#!/usr/bin/env bash
#
# Rehearse a restore, without touching anything real.
#
#   sudo ./scripts/drill.sh                 # newest backup available
#   sudo ./scripts/drill.sh ./backups/neural_log-20260920T030000Z.db.gz
#   sudo ./scripts/drill.sh db/2026/09/neural_log-20260920T030000Z.db.gz
#
# ## What this proves that a checksum does not
#
# `PRAGMA integrity_check` says the file is a valid SQLite database. It does not
# say the application can run on it, and those are different claims. A backup
# taken before a migration, a database whose file ownership the container cannot
# write to, an archive truncated on upload so it decompresses to a shorter but
# structurally valid file - all of them pass an integrity check and all of them
# fail a restore.
#
# So this does the actual thing: unpacks the backup into a scratch directory,
# starts a real container against it on a loopback port, waits for the health
# check to pass, reads some rows back out, and destroys the lot. If it finishes,
# a restore will work, because a restore is what just happened.
#
# ## What it does not touch
#
# The live database, the running containers, the compose project. Everything
# happens in a temporary directory under a container with its own name and a
# port bound to 127.0.0.1. Run it on the production instance in the middle of
# the afternoon; nobody will notice.
set -euo pipefail

BUCKET="${NEURAL_LOG_BACKUP_BUCKET:-}"
PREFIX="${NEURAL_LOG_BACKUP_PREFIX:-db}"
IMAGE="${NEURAL_LOG_IMAGE:-ghcr.io/skywalker1910/neural-log:latest}"
PORT="${NEURAL_LOG_DRILL_PORT:-8099}"
CONTAINER="neurallog-drill-$$"
SOURCE="${1:-}"

WORK="$(mktemp -d)"

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

log()  { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "DRILL FAILED: $1"; exit 1; }

# --- find a backup -----------------------------------------------------------

if [[ -z "$SOURCE" ]]; then
    # Local first. It is the copy a real 2am restore would reach for, so it is
    # the copy worth rehearsing with.
    # shellcheck disable=SC2012  # filenames are timestamps, so ls sorts correctly
    SOURCE="$(ls -1t ./backups/*.db.gz 2>/dev/null | head -1 || true)"

    if [[ -z "$SOURCE" && -n "$BUCKET" ]]; then
        log "no local backups; looking in s3://$BUCKET/$PREFIX/"
        SOURCE="$(aws s3 ls "s3://$BUCKET/$PREFIX/" --recursive \
            | sort -k1,2 | tail -1 | awk '{print $4}')"
    fi

    [[ -n "$SOURCE" ]] || fail "no backups found locally or in S3"
fi

log "drilling with $SOURCE"

ARCHIVE="$WORK/backup.db.gz"
if [[ -f "$SOURCE" ]]; then
    cp "$SOURCE" "$ARCHIVE"
else
    [[ -n "$BUCKET" ]] || fail "$SOURCE is not a local file and no bucket is set"
    aws s3 cp "s3://$BUCKET/$SOURCE" "$ARCHIVE" --only-show-errors \
        || fail "could not download $SOURCE - the backup credentials are PutObject-only, so run this with your own AWS profile"
fi

# --- unpack and inspect ------------------------------------------------------

DATA="$WORK/data"
mkdir -p "$DATA"
gunzip -c "$ARCHIVE" > "$DATA/neural_log.db" || fail "archive would not decompress"

INTEGRITY="$(sqlite3 "$DATA/neural_log.db" 'PRAGMA integrity_check;')"
[[ "$INTEGRITY" == "ok" ]] || fail "integrity check: $INTEGRITY"

BEFORE_USERS="$(sqlite3 "$DATA/neural_log.db" 'SELECT COUNT(*) FROM users;')"
BEFORE_DAYS="$(sqlite3 "$DATA/neural_log.db" 'SELECT COUNT(*) FROM daily_log;')"
BEFORE_SCHEMA="$(sqlite3 "$DATA/neural_log.db" 'SELECT MAX(version) FROM schema_migrations;')"
log "archive holds $BEFORE_USERS users, $BEFORE_DAYS logged days, schema $BEFORE_SCHEMA"

[[ "$BEFORE_USERS" -gt 0 ]] || fail "the backup has no users in it"

# The container runs as UID 10001 and needs to write - WAL, and any migration
# the current image is newer than this backup. Getting this wrong is the most
# common reason a restore "works" and then the app will not start.
chown -R 10001:10001 "$DATA"

# --- boot the real application on it -----------------------------------------

log "starting $IMAGE against the restored copy on 127.0.0.1:$PORT"
docker run --rm -d \
    --name "$CONTAINER" \
    -v "$DATA:/data" \
    -e NEURAL_LOG_ENV=production \
    -e SECRET_KEY="drill-only-$(head -c 24 /dev/urandom | base64 | tr -d '/+=')" \
    -e REGISTRATION_MODE=closed \
    -e DATABASE=/data/neural_log.db \
    -p "127.0.0.1:$PORT:8000" \
    "$IMAGE" >/dev/null || fail "the container would not start"

for attempt in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
        log "healthy after ${attempt}s"
        break
    fi
    [[ "$attempt" -lt 30 ]] || {
        log "--- container logs ---"
        docker logs "$CONTAINER" 2>&1 | tail -30
        fail "never became healthy"
    }
    sleep 1
done

# A health check proves the database opens. This proves the app serves from it:
# the sign-in page renders, and an unauthenticated API call is refused rather
# than erroring.
curl -fsS "http://127.0.0.1:$PORT/login" >/dev/null || fail "the sign-in page did not render"

STATUS="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/current-user")"
[[ "$STATUS" == "302" || "$STATUS" == "401" ]] || fail "expected an auth redirect, got $STATUS"

# --- confirm the data survived the round trip ---------------------------------

AFTER_USERS="$(sqlite3 "$DATA/neural_log.db" 'SELECT COUNT(*) FROM users;')"
AFTER_DAYS="$(sqlite3 "$DATA/neural_log.db" 'SELECT COUNT(*) FROM daily_log;')"
AFTER_SCHEMA="$(sqlite3 "$DATA/neural_log.db" 'SELECT MAX(version) FROM schema_migrations;')"

[[ "$AFTER_USERS" == "$BEFORE_USERS" ]] || fail "users went from $BEFORE_USERS to $AFTER_USERS"
[[ "$AFTER_DAYS" == "$BEFORE_DAYS" ]] || fail "logged days went from $BEFORE_DAYS to $AFTER_DAYS"

if [[ "$AFTER_SCHEMA" != "$BEFORE_SCHEMA" ]]; then
    # Not a failure. The backup predates a migration and the image applied it on
    # boot, which is precisely the path a real restore takes - worth saying out
    # loud rather than passing over in silence.
    log "note: migrations advanced the restored copy from $BEFORE_SCHEMA to $AFTER_SCHEMA"
fi

log "PASSED - $AFTER_USERS users and $AFTER_DAYS logged days served by a real container"
log "nothing was changed; the scratch copy is being deleted now"
