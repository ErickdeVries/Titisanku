#!/bin/sh
# Automatic MongoDB safety backup for KETURUNANKU.
# Dumps the app database to the persistent /app volume and keeps the last N
# snapshots. Runs hourly via cron so accidental data loss always has a
# recent restore point. Restore with:
#   mongorestore --drop --gzip --nsInclude='test_database.*' /app/backups/<dir>
set -eu

DB_NAME="test_database"
MONGO_URL="mongodb://localhost:27017"
DEST_ROOT="/app/backups"
KEEP=24  # keep last 24 hourly snapshots (~1 day)

TS="$(date +%Y%m%d_%H%M%S)"
DEST="$DEST_ROOT/dump_$TS"
mkdir -p "$DEST_ROOT"

/usr/bin/mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --out="$DEST" >/dev/null 2>&1 || {
    echo "$(date) db_backup: mongodump failed" >> "$DEST_ROOT/backup.log"
    exit 1
}
echo "$(date) db_backup: ok -> $DEST" >> "$DEST_ROOT/backup.log"

# Prune old snapshots, keep the newest $KEEP.
cd "$DEST_ROOT" || exit 0
ls -1dt dump_* 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -rf "$old"
done
