#!/usr/bin/env bash
# Installs the alert relay in the VM (Sales ticket 84): every 2 minutes,
# Alertmanager's firing alerts are copied to the host's share for the host's
# watchdog to mail. Run as root from this directory, after 13-backup.sh (it
# reads DEST from /etc/dw/backup.env):
#   sudo bash 15-alert-relay.sh
# Idempotent. Needs the stack's `observability` profile (make onprem-up).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ -r /etc/dw/backup.env ] || { echo "run 13-backup.sh first: /etc/dw/backup.env is missing" >&2; exit 1; }

DEBIAN_FRONTEND=noninteractive apt-get install -y -q jq curl </dev/null >/dev/null
install -d -m 755 /opt/dw/alert-relay
install -m 755 "$here/alert-relay/dw-alert-relay.sh" /opt/dw/alert-relay/dw-alert-relay.sh

cat > /etc/systemd/system/dw-alert-relay.service <<UNIT
[Unit]
Description=DW alert relay (Alertmanager to the host's share)
After=docker.service remote-fs.target

[Service]
Type=oneshot
ExecStart=/opt/dw/alert-relay/dw-alert-relay.sh
TimeoutStartSec=60
UNIT
cat > /etc/systemd/system/dw-alert-relay.timer <<UNIT
[Unit]
Description=DW alert relay schedule

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now dw-alert-relay.timer >/dev/null
systemctl start dw-alert-relay.service || true
systemctl list-timers dw-alert-relay.timer --no-pager
