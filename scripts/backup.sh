#!/usr/bin/env bash
#
# Nightly backup of the live database to S3.
#
# Run from the deployment directory on the instance, by systemd timer or cron:
#   0 3 * * *  cd /srv/neurallog && ./scripts/backup.sh >> /var/log/neurallog-backup.log 2>&1
#
# ## Why not just copy the file
#
# Because it is being written to. A `cp` of a live SQLite database can catch it
# mid-transaction and produce a file that opens fine and is missing a page - the
# worst kind of broken backup, the kind you find out about during a restore.
#
# `sqlite3 .backup` uses the online backup API: it takes a consistent snapshot
# while writers carry on, and in WAL mode it includes the write-ahead log. It is
# the only correct way to do this from outside the application.
#
# ## Why it verifies before uploading
#
# An unverified backup is a belief. `PRAGMA integrity_check` costs a second on a
# database this size and is the difference between "we have 30 backups" and "we
# have 30 copies of something".
set -euo pipefail
umask 077

DB="${NEURAL_LOG_DB:-./data/neural_log.db}"
BUCKET="${NEURAL_LOG_BACKUP_BUCKET:-}"
PREFIX="${NEURAL_LOG_BACKUP_PREFIX:-db}"
KEEP_LOCAL="${NEURAL_LOG_KEEP_LOCAL:-3}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SNAPSHOT="$WORK/neural_log-$STAMP.db"

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [[ -z "$BUCKET" && "${NEURAL_LOG_BACKUP_LOCAL_ONLY:-0}" != "1" ]]; then
    log "FATAL: set NEURAL_LOG_BACKUP_BUCKET or explicitly set NEURAL_LOG_BACKUP_LOCAL_ONLY=1"
    exit 1
fi

if [[ ! "$KEEP_LOCAL" =~ ^[1-9][0-9]*$ ]]; then
    log "FATAL: NEURAL_LOG_KEEP_LOCAL must be a positive integer"
    exit 1
fi

if [[ ! -f "$DB" ]]; then
    log "FATAL: no database at $DB"
    exit 1
fi

log "snapshotting $DB"
sqlite3 "$DB" ".backup '$SNAPSHOT'"

log "verifying the snapshot"
INTEGRITY="$(sqlite3 "$SNAPSHOT" 'PRAGMA integrity_check;')"
if [[ "$INTEGRITY" != "ok" ]]; then
    log "FATAL: integrity check failed: $INTEGRITY"
    exit 1
fi

# A sanity figure in the log, so a backup that silently started copying an empty
# database is visible without downloading anything.
USERS="$(sqlite3 "$SNAPSHOT" 'SELECT COUNT(*) FROM users;')"
DAYS="$(sqlite3 "$SNAPSHOT" 'SELECT COUNT(*) FROM daily_log;')"
log "ok - $USERS users, $DAYS logged days"

gzip -9 "$SNAPSHOT"
SNAPSHOT="$SNAPSHOT.gz"
SIZE="$(du -h "$SNAPSHOT" | cut -f1)"

# A copy on the instance as well, for the restore you need at 2am when you would
# rather not be discovering whether your AWS credentials still work.
mkdir -p ./backups
cp "$SNAPSHOT" "./backups/$(basename "$SNAPSHOT")"
# shellcheck disable=SC2012  # filenames here are timestamps, so ls is safe
ls -1t ./backups/*.db.gz 2>/dev/null | tail -n +"$((KEEP_LOCAL + 1))" | xargs -r rm --

if [[ -n "$BUCKET" ]]; then
    KEY="s3://$BUCKET/$PREFIX/$(date -u +%Y/%m)/neural_log-$STAMP.db.gz"
    log "uploading $SIZE to $KEY"
    aws s3 cp "$SNAPSHOT" "$KEY" --only-show-errors
else
    log "local-only backup; S3 replication is not configured"
fi

log "done"
