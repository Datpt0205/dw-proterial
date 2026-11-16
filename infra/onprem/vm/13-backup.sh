#!/usr/bin/env bash
# Installs the DW backup job in the VM: the script, its settings and three
# systemd timers (nightly 02:15, WAL hourly, restore test monthly). Run as root
# from this directory, after 12-backup-mount.sh:
#   sudo bash 13-backup.sh /srv/dw/app [project]
# where /srv/dw/app is the directory holding the stack's compose files and .env.
# Idempotent.
set -euo pipefail
COMPOSE_DIR="${1:?compose directory (with .env)}"
PROJECT="${2:-dw}"
here="$(cd "$(dirname "$0")" && pwd)"

DEBIAN_FRONTEND=noninteractive apt-get install -y -q jq </dev/null >/dev/null
install -d -m 755 /opt/dw/backup /etc/dw
install -m 755 "$here/backup/dw-backup.sh" /opt/dw/backup/dw-backup.sh

cat > /etc/dw/backup.env <<EOF
DW_COMPOSE_DIR=$COMPOSE_DIR
COMPOSE_PROJECT_NAME=$PROJECT
DEST=/srv/dw/backup
WAL_LOCAL=/srv/dw/wal-archive
EOF
chmod 600 /etc/dw/backup.env

# The WAL archive the postgres container writes (uid 70 in the alpine image).
install -d -m 700 -o 70 -g 70 /srv/dw/wal-archive

unit() {  # name, schedule, mode, timeout
    cat > "/etc/systemd/system/dw-backup-$1.service" <<EOF
[Unit]
Description=DW backup ($3)
Requires=docker.service
After=docker.service remote-fs.target

[Service]
Type=oneshot
ExecStart=/opt/dw/backup/dw-backup.sh $3
TimeoutStartSec=$4
Nice=10
IOSchedulingClass=idle
EOF
    cat > "/etc/systemd/system/dw-backup-$1.timer" <<EOF
[Unit]
Description=DW backup ($3) schedule

[Timer]
OnCalendar=$2
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF
}
unit nightly '*-*-* 02:15:00' nightly 4h
unit wal     'hourly'          wal     30min
unit verify  '*-*-01 04:30:00' verify  2h

systemctl daemon-reload
systemctl enable --now dw-backup-nightly.timer dw-backup-wal.timer dw-backup-verify.timer >/dev/null
systemctl list-timers 'dw-backup-*' --no-pager
