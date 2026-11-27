#!/usr/bin/env bash
# Copies what Alertmanager has firing to the host's share, where the host's
# watchdog (host-watchdog.ps1) reads it and mails a person (Sales ticket 84).
# One mail sender, the host's; no second secret lives in the VM.
#
# Writes $DEST/status/alerts.json only from an answer Alertmanager gave and jq
# parsed, through a temporary file and a rename, as dw-backup.sh's status()
# does. Any failure writes nothing: the file goes stale, and the host reports
# a stale file as the relay failing, never as "no alerts" (curl without
# --fail once turned a 404 page into a passing step: failure-modes #1).
# Alertmanager answering an empty list is told apart from a pipeline that is
# down by the always-firing Watchdog alert, which the host requires.
set -euo pipefail
. /etc/dw/backup.env
URL="${DW_ALERTMANAGER_URL:-http://127.0.0.1:9093}/api/v2/alerts?active=true&silenced=false&inhibited=false"

mountpoint -q "$DEST" || ls "$DEST" >/dev/null 2>&1   # wake the automount
mountpoint -q "$DEST" || { echo "backup share not mounted at $DEST" >&2; exit 1; }

answer="$(curl -fsS --max-time 20 "$URL")"
# One entry per alert: its name, the label that says which one (lane,
# channel, queue or job), its summary, and `notice` ("event" for an alert
# whose clearing fixes nothing, which the host then does not mail as "OK
# again"). Nothing else leaves the VM.
alerts="$(jq -c '[.[] | {
    name: .labels.alertname,
    which: (.labels.lane // .labels.channel // .labels.queue // .labels.job // ""),
    severity: (.labels.severity // ""),
    notice: (.labels.notice // ""),
    summary: (.annotations.summary // "")
  }]' <<<"$answer")"

mkdir -p "$DEST/status"
tmp="$DEST/status/alerts.json.tmp"
printf '{"time":"%s","alerts":%s}\n' "$(date -Is)" "$alerts" > "$tmp"
mv "$tmp" "$DEST/status/alerts.json"
