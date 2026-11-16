#!/usr/bin/env bash
# The VM's side of the host link (09-internal-link.ps1): the adapter with MAC
# 00:15:5d:0a:00:02 gets 10.250.0.2/30, no gateway and no DNS (the LAN adapter
# keeps both), and `dw-host` now names the host's link address, so the backup
# mount and DW's model URL survive the LAN changing address. Run as root.
# Idempotent.
set -euo pipefail
MAC=00:15:5d:0a:00:02
IFACE="$(ip -o link | awk -v m="$MAC" 'tolower($0) ~ m {sub(":","",$2); print $2; exit}')"
[ -n "$IFACE" ] || { echo "no adapter with MAC $MAC (run 09-internal-link.ps1 first)" >&2; exit 1; }

cat > /etc/netplan/60-dw-internal.yaml <<EOF
network:
  version: 2
  ethernets:
    dw-internal:
      match:
        macaddress: "$MAC"
      set-name: dwlink0
      addresses: [10.250.0.2/30]
      dhcp4: false
      dhcp6: false
      link-local: []
EOF
chmod 600 /etc/netplan/60-dw-internal.yaml
netplan apply

sed -i '/[[:space:]]dw-host$/d' /etc/hosts
echo "10.250.0.1 dw-host" >> /etc/hosts

ip -4 -brief addr show dwlink0
ping -c 2 -W 2 dw-host | tail -1
