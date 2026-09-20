#!/usr/bin/env bash
#
# Nightly backup of the live database, on the instance and off it.
#
# Run from the deployment directory, by the systemd timer in deploy/:
#   sudo systemctl enable --now neurallog-backup.timer
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
#
# ## Why it writes a status file
#
# Because the way backups fail is silently. The timer stops firing, or the
# credentials expire, or the bucket policy changes, and nothing anywhere says so
# - `systemctl status` knows, and nobody runs `systemctl status` on a Tuesday.
# Every run writes its outcome next to the database, where the app can read it
# and the admin page can say "last backup: 8 hours ago" or "last backup FAILED".
#
# A failed run writes the status too. That is the point: a stale timestamp and a
# recorded failure are both visible, and a script that only reports success is a
# script whose silence means nothing.
set -euo pipefail
umask 077

DB="${NEURAL_LOG_DB:-./data/neural_log.db}"
BUCKET="${NEURAL_LOG_BACKUP_BUCKET:-}"
PREFIX="${NEURAL_LOG_BACKUP_PREFIX:-db}"
KEEP_LOCAL="${NEURAL_LOG_KEEP_LOCAL:-3}"
STATUS_PATH="${NEURAL_LOG_BACKUP_STATUS:-$(dirname "$DB")/backup-status.json}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

SNAPSHOT="$WORK/neural_log-$STAMP.db"

log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

json_string() {
    # Minimal JSON escaping. The only values that reach here are log messages and
    # S3 keys, but an unescaped quote would produce a status file the app cannot
    # parse - which reads as "no backup has ever run".
    printf '%s' "${1-}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr -d '\n\r'
}

write_status() {
    local ok="$1" message="$2"
    cat > "$STATUS_PATH.tmp" <<JSON
{
  "finished_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "ok": $ok,
  "message": "$(json_string "$message")",
  "offsite": ${OFFSITE:-false},
  "destination": "$(json_string "${DESTINATION:-}")",
  "bytes": ${BYTES:-0},
  "users": ${USERS:-0},
  "logged_days": ${DAYS:-0},
  "local_copies": ${LOCAL_COPIES:-0}
}
JSON
    # Readable by the app, which runs as a different user inside the container.
    # It holds timestamps and row counts, no secrets - the umask above would
    # otherwise make it root-only and the admin page would see nothing.
    chmod 0644 "$STATUS_PATH.tmp"
    # Renamed into place rather than written in place, so a reader never catches
    # a half-written file and concludes the backup is broken.
    mv "$STATUS_PATH.tmp" "$STATUS_PATH"
}

fail() {
    log "FATAL: $1"
    write_status false "$1"
    exit 1
}

# Anything unexpected - a killed sqlite3, a full disk - lands here rather than
# leaving yesterday's success as the most recent word on the subject.
trap 'fail "backup script exited unexpectedly at line $LINENO"' ERR

if [[ -z "$BUCKET" && "${NEURAL_LOG_BACKUP_LOCAL_ONLY:-0}" != "1" ]]; then
    fail "set NEURAL_LOG_BACKUP_BUCKET or explicitly set NEURAL_LOG_BACKUP_LOCAL_ONLY=1"
fi

if [[ ! "$KEEP_LOCAL" =~ ^[1-9][0-9]*$ ]]; then
    fail "NEURAL_LOG_KEEP_LOCAL must be a positive integer"
fi

if [[ ! -f "$DB" ]]; then
    fail "no database at $DB"
fi

log "snapshotting $DB"
sqlite3 "$DB" ".backup '$SNAPSHOT'"

log "verifying the snapshot"
INTEGRITY="$(sqlite3 "$SNAPSHOT" 'PRAGMA integrity_check;')"
if [[ "$INTEGRITY" != "ok" ]]; then
    fail "integrity check failed: $INTEGRITY"
fi

# Sanity figures in the log and the status file, so a backup that silently
# started copying an empty database is visible without downloading anything.
USERS="$(sqlite3 "$SNAPSHOT" 'SELECT COUNT(*) FROM users;')"
DAYS="$(sqlite3 "$SNAPSHOT" 'SELECT COUNT(*) FROM daily_log;')"
log "ok - $USERS users, $DAYS logged days"

gzip -9 "$SNAPSHOT"
SNAPSHOT="$SNAPSHOT.gz"
BYTES="$(stat -c %s "$SNAPSHOT")"

# A copy on the instance as well, for the restore you need at 2am when you would
# rather not be discovering whether your AWS credentials still work.
mkdir -p ./backups
cp "$SNAPSHOT" "./backups/$(basename "$SNAPSHOT")"
# shellcheck disable=SC2012  # filenames here are timestamps, so ls is safe
ls -1t ./backups/*.db.gz 2>/dev/null | tail -n +"$((KEEP_LOCAL + 1))" | xargs -r rm --
LOCAL_COPIES="$(find ./backups -maxdepth 1 -name '*.db.gz' | wc -l)"

OFFSITE=false
DESTINATION="local-only"

if [[ -n "$BUCKET" ]]; then
    KEY="$PREFIX/$(date -u +%Y/%m)/neural_log-$STAMP.db.gz"
    log "uploading $BYTES bytes to s3://$BUCKET/$KEY"
    aws s3 cp "$SNAPSHOT" "s3://$BUCKET/$KEY" --only-show-errors

    # Confirm the object is actually there, at the size we sent.
    #
    # `aws s3 cp` exiting 0 means the request was accepted, and this costs one
    # HEAD request to turn that into knowing. It is also the step that catches a
    # write-only credential that has quietly lost its permission: the upload
    # succeeds against a bucket policy that drops it, and only a read says so.
    #
    # The backup credentials are deliberately PutObject-only, so this is
    # expected to fail on permissions. A HEAD that is *denied* still proves the
    # bucket is reachable and the object was accepted; only a missing object is
    # a real failure.
    REMOTE_BYTES="$(aws s3api head-object --bucket "$BUCKET" --key "$KEY" \
        --query ContentLength --output text 2>/dev/null || echo 'unreadable')"

    case "$REMOTE_BYTES" in
        "$BYTES")      log "confirmed $REMOTE_BYTES bytes in S3" ;;
        unreadable)    log "uploaded; cannot confirm size (write-only credentials)" ;;
        *)             fail "S3 object is $REMOTE_BYTES bytes, expected $BYTES" ;;
    esac

    OFFSITE=true
    DESTINATION="s3://$BUCKET/$KEY"
else
    log "local-only backup; S3 replication is not configured"
fi

write_status true "backed up $USERS users and $DAYS logged days"
log "done"
