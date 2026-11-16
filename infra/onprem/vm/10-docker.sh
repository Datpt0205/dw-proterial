#!/usr/bin/env bash
# Docker Engine in the DW VM (Ubuntu 24.04), from Docker's own apt repository,
# held at the version installed so unattended-upgrades never moves it.
# Run as root (sudo). Idempotent.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
apt-mark hold docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null

# live-restore: containers keep running while dockerd itself restarts (an
# upgrade); logs rotate even for a container whose compose file forgot to.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "live-restore": true,
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
systemctl enable --now docker containerd >/dev/null
systemctl restart docker

usermod -aG docker dw
docker version --format 'docker {{.Server.Version}}'
docker compose version
