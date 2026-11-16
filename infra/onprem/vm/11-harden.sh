#!/usr/bin/env bash
# Hardening of the DW VM (Ubuntu 24.04). Run as root (sudo). Idempotent.
#  - firewall: only SSH and the portal (80/443) come in
#  - SSH: keys only, no root
#  - security updates install themselves, never reboot on their own
#  - a small swap so memory pressure slows a service instead of OOM-killing it
#
# Docker publishes container ports through its own iptables chains, ahead of
# ufw: the compose files must publish only Caddy (80/443) on all addresses,
# and everything else on 127.0.0.1 or not at all. `ss -ltnp` after `compose up`
# is the check.
set -euo pipefail

# --- firewall --------------------------------------------------------------------
apt-get install -y -q ufw >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp  comment 'ssh (keys only)' >/dev/null
ufw allow 80/tcp  comment 'portal, redirect to https' >/dev/null
ufw allow 443/tcp comment 'portal' >/dev/null
ufw --force enable >/dev/null

# --- ssh -------------------------------------------------------------------------
cat > /etc/ssh/sshd_config.d/60-dw.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF
systemctl reload ssh

# --- security updates only, no automatic reboot ------------------------------------
apt-get install -y -q unattended-upgrades >/dev/null
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat > /etc/apt/apt.conf.d/52dw-no-auto-reboot <<'EOF'
Unattended-Upgrade::Automatic-Reboot "false";
EOF

# --- swap: 4 GB, used only under pressure ------------------------------------------
if ! swapon --show | grep -q '/swapfile'; then
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
    swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/60-dw.conf
sysctl -q --system

# --- report ----------------------------------------------------------------------
ufw status verbose | sed -n '1,12p'
sshd -T | grep -E '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication) '
systemctl is-enabled unattended-upgrades
swapon --show
chronyc tracking | grep -E 'Reference ID|System time'
