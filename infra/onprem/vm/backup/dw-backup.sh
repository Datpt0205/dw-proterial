#!/usr/bin/env bash
# DW backups on the VM, written to the host's B:\DW-Backup (mounted at
# $DEST by 12-backup-mount.sh). Three modes, run by systemd timers (13-backup.sh):
#
#   nightly  02:15  Postgres dumps (dw, keycloak, the roles), a base backup on
#                   Sundays (or when none is a week old), a Qdrant snapshot, the
#                   object store synced (changed and deleted files kept aside),
#                   .env and Caddy's CA; checksums; then retention.
#   wal      hourly the local WAL archive (docker-compose.backup.yml) copied to
#                   $DEST/wal; local segments already copied and 2 days old go.
#   verify   monthly the newest nightly restored into throwaway containers and
#                   checked (restore-test below); a backup never restored is not
#                   one.
#
# The host watchdog reads $DEST/status: last-ok.json older than 26 h, or
# last-verify.json older than 35 days or failed, becomes a mail. This script
# never mails: the VM has no mail and the host already does.
#
# Retention: a nightly is kept 7 days; a Sunday's 28 days; the 1st of a month's
# 365 days. Base backups: the newest 5. WAL: back to the oldest kept base
# backup. Changed/deleted objects: 90 days.
#
# Settings: /etc/dw/backup.env (DW_COMPOSE_DIR, COMPOSE_PROJECT_NAME, DEST,
# WAL_LOCAL; the stack's own .env gives the Postgres and S3 credentials).
set -euo pipefail
umask 077

MODE="${1:?nightly|wal|verify}"
[ -f /etc/dw/backup.env ] && . /etc/dw/backup.env
DW_COMPOSE_DIR="${DW_COMPOSE_DIR:?}"
PROJECT="${COMPOSE_PROJECT_NAME:-dw}"
DEST="${DEST:-/srv/dw/backup}"
WAL_LOCAL="${WAL_LOCAL:-/srv/dw/wal-archive}"
RCLONE_IMAGE="rclone/rclone:1.75.1"
PG_IMAGE="postgres:16.15-alpine"
QDRANT_IMAGE="qdrant/qdrant:v1.20.1"

set -a; . "$DW_COMPOSE_DIR/.env"; set +a
PG="${PROJECT}-postgres-1"
PGU="${POSTGRES_USER:?}"
QDRANT_URL="http://127.0.0.1:${DW_QDRANT_HOST_PORT:-6333}"
S3_URL="http://127.0.0.1:${DW_MINIO_HOST_PORT:-9000}"

log() { echo "[$(date -Is)] $MODE: $*"; }
status() { mkdir -p "$DEST/status"; printf '%s\n' "$2" > "$DEST/status/$1.tmp" && mv "$DEST/status/$1.tmp" "$DEST/status/$1"; }
fail() { status "last-error.json" "{\"time\":\"$(date -Is)\",\"mode\":\"$MODE\",\"error\":\"$1\"}"; log "FAILED: $1"; exit 1; }
trap 'fail "line $LINENO exited $?"' ERR

# One run at a time, per mode.
exec 9>"/run/dw-backup-$MODE.lock"
flock -n 9 || { log "another $MODE run holds the lock"; exit 0; }

mountpoint -q "$DEST" || ls "$DEST" >/dev/null 2>&1   # wake the automount
mountpoint -q "$DEST" || fail "backup share not mounted at $DEST"

qcurl() { curl -fsS ${QDRANT_API_KEY:+-H "api-key: $QDRANT_API_KEY"} "$@"; }
rclone_s3() {
    docker run --rm --network host -v "$DEST:/dest" \
        -e RCLONE_CONFIG_S3_TYPE=s3 -e RCLONE_CONFIG_S3_PROVIDER=Other \
        -e RCLONE_CONFIG_S3_ENDPOINT="$S3_URL" \
        -e RCLONE_CONFIG_S3_ACCESS_KEY_ID="$MINIO_ROOT_USER" \
        -e RCLONE_CONFIG_S3_SECRET_ACCESS_KEY="$MINIO_ROOT_PASSWORD" \
        "$RCLONE_IMAGE" "$@"
}

nightly() {
    local day; day="$(date +%F)"
    local out="$DEST/daily/$day" tmp="$DEST/daily/$day.partial"
    rm -rf "$tmp"; mkdir -p "$tmp"

    log "postgres: roles"
    docker exec "$PG" pg_dumpall -U "$PGU" --globals-only | gzip > "$tmp/globals.sql.gz"
    # The list is read, not assumed: a query that fails stops the run (a silent
    # skip once left a "successful" nightly with no dump in it, 2026-11-16).
    local dbs; dbs="$(docker exec "$PG" psql -U "$PGU" -d postgres -Atc \
        "select datname from pg_database where datname in ('dw','keycloak') order by 1")"
    grep -qx dw <<<"$dbs" || fail "database dw not found in $PG"
    for db in $dbs; do
        log "postgres: $db"
        docker exec "$PG" pg_dump -U "$PGU" -Fc "$db" > "$tmp/$db.dump"
    done
    printf '%s\n' $dbs > "$tmp/databases.txt"

    local newest_base; newest_base="$(ls -1d "$DEST"/base/20* 2>/dev/null | tail -1 || true)"
    if [ "$(date +%u)" = 7 ] || [ -z "$newest_base" ] || [ -n "$(find "$newest_base" -maxdepth 0 -mtime +6)" ]; then
        log "postgres: base backup"
        mkdir -p "$DEST/base/$day.partial"
        docker exec "$PG" pg_basebackup -U "$PGU" -D - -Ft -z -X fetch -c fast > "$DEST/base/$day.partial/base.tar.gz"
        rm -rf "$DEST/base/$day"; mv "$DEST/base/$day.partial" "$DEST/base/$day"
    fi

    log "qdrant: snapshot"
    # What the store holds now, for the restore test to compare against.
    qcurl "$QDRANT_URL/collections" | jq -r '.result.collections[].name' | while read -r c; do
        printf '%s\t%s\n' "$c" "$(qcurl "$QDRANT_URL/collections/$c" | jq -r '.result.points_count')"
    done > "$tmp/qdrant-counts.tsv"
    local snap; snap="$(qcurl -X POST "$QDRANT_URL/snapshots" | jq -r '.result.name')"
    qcurl -o "$tmp/qdrant.snapshot" "$QDRANT_URL/snapshots/$snap"
    qcurl -X DELETE "$QDRANT_URL/snapshots/$snap" >/dev/null

    log "objects: sync"
    mkdir -p "$DEST/objects/current" "$DEST/objects/changed"
    rclone_s3 sync s3: /dest/objects/current --backup-dir "/dest/objects/changed/$day" \
        --exclude 'dw-pg-backups/**' --exclude 'langfuse/**' --checksum -q
    rclone_s3 size s3: --exclude 'dw-pg-backups/**' --exclude 'langfuse/**' --json > "$tmp/objects-size.json"

    log "config"
    install -m 600 "$DW_COMPOSE_DIR/.env" "$tmp/env"
    if docker volume inspect "${PROJECT}_caddy-data" >/dev/null 2>&1; then
        docker run --rm -v "${PROJECT}_caddy-data:/d:ro" alpine:3.20.10 tar -C /d -czf - . > "$tmp/caddy-data.tar.gz"
    fi

    (cd "$tmp" && sha256sum -b * > SHA256SUMS)
    rm -rf "$out"; mv "$tmp" "$out"

    retention
    local size; size="$(du -sb "$out" | cut -f1)"
    status "last-ok.json" "{\"time\":\"$(date -Is)\",\"dir\":\"daily/$day\",\"bytes\":$size}"
    log "done: daily/$day ($size bytes)"
}

retention() {
    local now; now="$(date +%s)"
    for d in "$DEST"/daily/20??-??-??; do
        [ -d "$d" ] || continue
        local name age dow dom
        name="$(basename "$d")"
        age=$(( (now - $(date -d "$name" +%s)) / 86400 ))
        dow="$(date -d "$name" +%u)"; dom="$(date -d "$name" +%d)"
        if [ "$age" -le 7 ] || { [ "$dow" = 7 ] && [ "$age" -le 28 ]; } || { [ "$dom" = 01 ] && [ "$age" -le 365 ]; }; then
            continue
        fi
        log "retention: drop daily/$name"; rm -rf "$d"
    done
    rm -rf "$DEST"/daily/*.partial "$DEST"/base/*.partial
    ls -1d "$DEST"/base/20* 2>/dev/null | head -n -5 | while read -r b; do log "retention: drop base/$(basename "$b")"; rm -rf "$b"; done
    local oldest_base; oldest_base="$(ls -1d "$DEST"/base/20* 2>/dev/null | head -1 || true)"
    if [ -n "$oldest_base" ] && [ -d "$DEST/wal" ]; then
        find "$DEST/wal" -name '*.gz' ! -newer "$oldest_base" -delete
    fi
    find "$DEST/objects/changed" -mindepth 1 -maxdepth 1 -type d -mtime +90 -exec rm -rf {} + 2>/dev/null || true
}

wal() {
    mkdir -p "$DEST/wal"
    local n=0
    for f in "$WAL_LOCAL"/*.gz; do
        [ -e "$f" ] || continue
        local b; b="$(basename "$f")"
        if [ ! -e "$DEST/wal/$b" ] || [ "$(stat -c %s "$f")" != "$(stat -c %s "$DEST/wal/$b")" ]; then
            cp "$f" "$DEST/wal/$b.part" && mv "$DEST/wal/$b.part" "$DEST/wal/$b"; n=$((n + 1))
        fi
    done
    # Local copies go only once they are on the share and two days old.
    for f in "$WAL_LOCAL"/*.gz; do
        [ -e "$f" ] || continue
        local b; b="$(basename "$f")"
        if [ -e "$DEST/wal/$b" ] && [ -n "$(find "$f" -mmin +2880)" ]; then rm -f "$f"; fi
    done
    status "last-wal.json" "{\"time\":\"$(date -Is)\",\"copied\":$n}"
    log "copied $n segment(s)"
}

# Restore test: the newest nightly into throwaway containers, then checks that
# would fail on an empty or broken backup. Leaves nothing behind.
verify() {
    local day; day="$(ls -1d "$DEST"/daily/20??-??-?? | tail -1)"
    [ -n "$day" ] || fail "no nightly backup to verify"
    # Throwaway containers and the local snapshot copy go however this ends:
    # fail() exits directly, so an ERR trap alone left them behind (measured).
    VERIFY_T="dwverify-$$"; VERIFY_WORK=""
    local t="$VERIFY_T"
    trap 'docker rm -f "$VERIFY_T-pg" "$VERIFY_T-qd" >/dev/null 2>&1 || true; [ -n "$VERIFY_WORK" ] && rm -rf "$VERIFY_WORK"' EXIT
    log "verifying $(basename "$day")"

    (cd "$day" && sha256sum -c --quiet SHA256SUMS) || fail "checksums do not match in $(basename "$day")"

    docker run -d --name "$t-pg" -e POSTGRES_PASSWORD=verify "$PG_IMAGE" >/dev/null
    for _ in $(seq 60); do docker exec "$t-pg" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
    gunzip -c "$day/globals.sql.gz" | docker exec -i "$t-pg" psql -U postgres -q -o /dev/null 2>/dev/null || true
    # Every database the nightly listed must be there and restore cleanly; dw must
    # come back with tables. A nightly missing its dump fails here, not silently.
    [ -s "$day/databases.txt" ] || fail "$(basename "$day") lists no databases"
    grep -qx dw "$day/databases.txt" || fail "$(basename "$day") has no dw database"
    local tables=0
    while read -r db; do
        [ -s "$day/$db.dump" ] || fail "$(basename "$day") has no dump for $db"
        docker exec "$t-pg" createdb -U postgres "$db"
        docker exec -i "$t-pg" pg_restore -U postgres -d "$db" --no-owner --exit-on-error < "$day/$db.dump"
        local n; n="$(docker exec "$t-pg" psql -U postgres -d "$db" -Atc "select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema')")"
        if [ "$db" = dw ] && [ "$n" -eq 0 ]; then fail "dw restored with no tables"; fi
        tables=$((tables + n))
    done < "$day/databases.txt"
    if [ -f "$day/dw.dump" ]; then
        docker exec "$t-pg" psql -U postgres -d dw -Atc "select version_num from alembic_version" >/dev/null 2>&1 \
            || log "note: dw has no alembic_version table"
    fi

    # A full-storage snapshot is restored when Qdrant starts (--storage-snapshot).
    # The share's files are root-only, so the snapshot is read from a local copy.
    local work; work="$(mktemp -d /var/tmp/dwverify.XXXX)"; VERIFY_WORK="$work"
    cp "$day/qdrant.snapshot" "$work/full.snapshot"; chmod 644 "$work/full.snapshot"; chmod 755 "$work"
    docker run -d --name "$t-qd" -p 127.0.0.1::6333 -v "$work:/snap:ro" "$QDRANT_IMAGE" \
        ./qdrant --storage-snapshot /snap/full.snapshot >/dev/null
    local qport; qport="$(docker port "$t-qd" 6333 | head -1 | cut -d: -f2)"
    for _ in $(seq 120); do curl -fsS "http://127.0.0.1:$qport/healthz" >/dev/null 2>&1 && break; sleep 1; done
    local cols=0
    while IFS=$'\t' read -r c want; do
        [ -n "$c" ] || continue
        local got; got="$(curl -fsS "http://127.0.0.1:$qport/collections/$c" | jq -r '.result.points_count')"
        # The store was live while the snapshot was taken: allow 1 % drift, never a loss.
        [ "$got" -ge $(( want * 99 / 100 )) ] || fail "qdrant $c restored $got points, the store had $want"
        cols=$((cols + 1))
    done < "$day/qdrant-counts.tsv"
    rm -rf "$work"

    local objs; objs="$(jq -r '.count' "$day/objects-size.json")"
    local cur; cur="$(find "$DEST/objects/current" -type f | wc -l)"
    [ "$cur" -ge "$objs" ] || fail "objects: backup holds $cur files, the store had $objs"

    status "last-verify.json" "{\"time\":\"$(date -Is)\",\"ok\":true,\"day\":\"$(basename "$day")\",\"tables\":$tables,\"qdrant_collections\":$cols,\"objects\":$objs}"
    log "ok: $tables tables, $cols qdrant collection snapshot(s), $objs objects"
}

case "$MODE" in
    nightly) nightly ;;
    wal) wal ;;
    verify) verify ;;
    *) fail "unknown mode $MODE" ;;
esac
