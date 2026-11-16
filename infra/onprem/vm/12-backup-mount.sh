#!/usr/bin/env bash
# Mounts the host's B:\DW-Backup share (08-backup-share.ps1) at /srv/dw/backup.
# Run as root: the SMB password comes on standard input, never as an argument:
#   ssh dw-host 'Get-Content C:\ProgramData\DW\backup-smb.cred' | ssh dw-vm 'sudo bash 12-backup-mount.sh'
# Idempotent. The host's address lives in one place, /etc/hosts as `dw-host`:
# the private host link (09-internal-link.ps1, 14-internal-link.sh), which the
# LAN's addressing never touches.
set -euo pipefail
HOST_IP="${1:-10.250.0.1}"
MNT=/srv/dw/backup
CRED=/root/.smb-dw-backup

# Read the password first: apt/dpkg below may read standard input too.
pass="$(cat | tr -d '\r\n')"
[ -n "$pass" ] || { echo "no password on stdin" >&2; exit 1; }

DEBIAN_FRONTEND=noninteractive apt-get install -y -q cifs-utils </dev/null >/dev/null

# The host's name, one owner.
sed -i '/[[:space:]]dw-host$/d' /etc/hosts
echo "${HOST_IP} dw-host" >> /etc/hosts
umask 077
printf 'username=dwbackup\npassword=%s\n' "$pass" > "$CRED"
unset pass

mkdir -p "$MNT"
line="//dw-host/DW-Backup $MNT cifs credentials=$CRED,uid=0,gid=0,file_mode=0600,dir_mode=0700,vers=3.1.1,seal,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=30 0 0"
sed -i "\#[[:space:]]$MNT[[:space:]]#d" /etc/fstab
echo "$line" >> /etc/fstab
systemctl daemon-reload
systemctl restart remote-fs.target
ls "$MNT" >/dev/null   # triggers the automount

probe="$MNT/.probe-$(hostname)"
date -Is > "$probe" && cat "$probe" >/dev/null && rm -f "$probe"
findmnt -n -o SOURCE,FSTYPE,OPTIONS "$MNT" | sed 's/password=[^,]*/password=***/'
echo "write test ok"
