#!/usr/bin/env bash
# Nightly Postgres backup for the sales_dw box.
#
# Why this exists (C2): the database lived on a single Docker volume with NO
# backup — a bad migration, an accidental `down -v`, or disk loss meant total,
# unrecoverable loss of every tenant's CRM data. This gives a daily recovery
# point. It is the FIRST line, not the last: a dump on the same box does not
# survive the box itself, so DEST_REMOTE below (an off-box copy) is the part to
# wire once a destination exists.
#
# Restore:  gunzip -c dw_YYYYmmdd_HHMMSS.dump.gz | \
#             docker exec -i dw-postgres-1 pg_restore -U dw_admin -d dw --clean --if-exists
#
# Install (on the server, as the ubuntu user):
#   crontab -e   →   15 2 * * *  /home/ubuntu/base_agent/scripts/backup_postgres.sh >> /home/ubuntu/pg_backups/backup.log 2>&1
set -euo pipefail

CONTAINER="${PG_CONTAINER:-dw-postgres-1}"
DB="${PG_DB:-dw}"
PG_USER="${PG_USER:-dw_admin}"
DEST="${BACKUP_DIR:-/home/ubuntu/pg_backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$DEST"
stamp="$(date +%Y%m%d_%H%M%S)"
out="$DEST/${DB}_${stamp}.dump.gz"

echo "[$(date -Is)] backup start → $out"
# -Fc = custom format (compressible, selective restore); piped through gzip.
# A tmp file + atomic mv so a crashed dump never leaves a truncated "backup".
tmp="$out.partial"
if sudo docker exec "$CONTAINER" pg_dump -U "$PG_USER" -Fc "$DB" | gzip > "$tmp"; then
  mv "$tmp" "$out"
  echo "[$(date -Is)] backup ok: $(du -h "$out" | cut -f1)"
else
  rm -f "$tmp"
  echo "[$(date -Is)] backup FAILED" >&2
  exit 1
fi

# Rotate: drop dumps older than KEEP_DAYS. Runs only after a successful dump so a
# run of failures never deletes the last good copy.
find "$DEST" -name "${DB}_*.dump.gz" -mtime "+${KEEP_DAYS}" -print -delete

# Off-box copy — the part that survives losing the box. Left as an explicit hole
# rather than a silent absence: point DEST_REMOTE at MinIO/S3/another host and
# uncomment. Example (MinIO via mc):
#   mc cp "$out" "${DEST_REMOTE:?set DEST_REMOTE}"
echo "[$(date -Is)] done"
