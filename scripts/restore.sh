#!/usr/bin/env bash
#
# Put a backup back.
#
#   ./scripts/restore.sh                       # newest backup in S3
#   ./scripts/restore.sh db/2026/09/neural_log-20260917T030000Z.db.gz
#   ./scripts/restore.sh ./backups/neural_log-20260917T030000Z.db.gz
#
# ## Run this before you need it
#
# A backup nobody has restored is a belief, not a backup. The failure modes are
# all silent - wrong bucket, wrong credentials, a `cp` that captured a
# half-written page, a gzip that was truncated on upload - and every one of them
# looks exactly like a working backup until the day it matters.
#
# So: restore into a scratch directory on a quiet afternoon, point a local app at
# it, and check your own logged days are there. That is the drill, and it is the
# only thing that turns the backup into a plan.
#
# ## What this does to the current database
#
# Moves it aside, never deletes it. If the restored file turns out to be worse
# than what was there, the displaced copy is sitting next to it with a timestamp.
set -euo pipefail

DB="${NEURAL_LOG_DB:-./data/neural_log.db}"
BUCKET="${NEURAL_LOG_BACKUP_BUCKET:-}"
PREFIX="${NEURAL_LOG_BACKUP_PREFIX:-db}"
SOURCE="${1:-}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [[ -z "$SOURCE" ]]; then
    [[ -n "$BUCKET" ]] || { log "FATAL: no argument and no NEURAL_LOG_BACKUP_BUCKET"; exit 1; }
    log "looking for the newest backup in s3://$BUCKET/$PREFIX/"
    SOURCE="$(aws s3 ls "s3://$BUCKET/$PREFIX/" --recursive \
        | sort -k1,2 | tail -1 | awk '{print $4}')"
    [[ -n "$SOURCE" ]] || { log "FATAL: no backups found"; exit 1; }
    log "newest is $SOURCE"
fi

ARCHIVE="$WORK/restore.db.gz"
if [[ -f "$SOURCE" ]]; then
    cp "$SOURCE" "$ARCHIVE"
else
    # The instance's own credentials are PutObject-only by design - see
    # docs/BACKUPS.md. Downloading is a deliberate, human-driven act, so it uses
    # your credentials rather than the ones sitting on a public-facing box.
    aws s3 cp "s3://$BUCKET/$SOURCE" "$ARCHIVE" --only-show-errors         || { log "FATAL: could not download - run this with your own AWS profile, not the instance's write-only one"; exit 1; }
fi

gunzip -c "$ARCHIVE" > "$WORK/restore.db"

# Verified before anything is moved, so a corrupt archive cannot take out a
# working database on its way past.
log "verifying"
INTEGRITY="$(sqlite3 "$WORK/restore.db" 'PRAGMA integrity_check;')"
[[ "$INTEGRITY" == "ok" ]] || { log "FATAL: integrity check failed: $INTEGRITY"; exit 1; }

USERS="$(sqlite3 "$WORK/restore.db" 'SELECT COUNT(*) FROM users;')"
DAYS="$(sqlite3 "$WORK/restore.db" 'SELECT COUNT(*) FROM daily_log;')"
VERSION="$(sqlite3 "$WORK/restore.db" 'SELECT MAX(version) FROM schema_migrations;')"
log "ok - $USERS users, $DAYS logged days, schema at $VERSION"

read -rp "Replace $DB with this? [y/N] " CONFIRM
[[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]] || { log "aborted"; exit 1; }

# Stopped first. Swapping a database out from under a running process leaves it
# holding a file handle to something that is no longer there.
#
# `compose ps --quiet` exits 0 with empty output when nothing is running, so the
# test has to be on the output rather than the status.
if [[ -n "$(docker compose ps --quiet app 2>/dev/null)" ]]; then
    log "stopping the app"
    docker compose stop app
    RESTART=1
fi

if [[ -f "$DB" ]]; then
    ASIDE="$DB.displaced-$(date -u +%Y%m%dT%H%M%SZ)"
    log "moving the current database to $ASIDE"
    mv "$DB" "$ASIDE"
    # The WAL and shared-memory files belong to the database that just moved.
    # Leaving them behind would have SQLite try to replay one database's journal
    # onto another's pages.
    rm -f "$DB-wal" "$DB-shm"
fi

mkdir -p "$(dirname "$DB")"
cp "$WORK/restore.db" "$DB"

# The container runs as UID 10001. A database restored by root is one the app
# can read and cannot write, which does not fail here - it fails the first time
# somebody logs a meal, hours later, with "attempt to write a readonly database".
#
# Matched to whoever owns the data directory rather than hard-coded, so this is
# also correct when running the script somewhere that is not the instance.
OWNER="$(stat -c '%u:%g' "$(dirname "$DB")")"
chown "$OWNER" "$DB"
log "restored, owned by $OWNER"

if [[ "${RESTART:-0}" == "1" ]]; then
    log "starting the app"
    docker compose start app
fi

log "done - check the app, and keep the displaced copy until you have"
