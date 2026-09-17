#!/usr/bin/env bash
# In-place deploy on a host that already holds the repo, the .env and the volumes.
#
#   scripts/deploy.sh <branch> [<environment>]
#
# environment is one of: dev | uat | production. It selects the compose overlay,
# and the overlay is what pins DW_API_PROFILE — so the environment a host runs
# as is decided by the argument to this script, never by whether somebody set a
# variable in .env correctly.
#
# The same script runs from GitHub Actions, from GitLab CI and by hand. It lived
# as four near-identical copies of this shell before; four copies drift, and the
# one that drifts is discovered during an incident.
set -euo pipefail

BRANCH="${1:?usage: deploy.sh <branch> [dev|uat|production]}"
ENVIRONMENT="${2:-dev}"
DEPLOY_DIR="${DEPLOY_DIR:-/home/ubuntu/base_agent}"
COMPOSE_BASE="infra/compose/docker-compose.yml"

case "$ENVIRONMENT" in
  dev) OVERLAY="" ;;
  uat) OVERLAY="-f infra/compose/docker-compose.uat.yml" ;;
  production) OVERLAY="-f infra/compose/docker-compose.prod.yml" ;;
  *) echo "unknown environment: $ENVIRONMENT (expected dev, uat or production)" >&2; exit 2 ;;
esac

cd "$DEPLOY_DIR"

echo ">> environment : $ENVIRONMENT"
echo ">> branch      : $BRANCH"
git fetch origin --quiet
git checkout -B "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
echo ">> HEAD        : $(git rev-parse --short HEAD) $(git log -1 --format=%s)"

# shellcheck disable=SC2086  # OVERLAY is a deliberate word-split of compose flags
COMPOSE=(docker compose --env-file .env -f "$COMPOSE_BASE" $OVERLAY)

"${COMPOSE[@]}" --profile full up --build -d

# Migrations run as the one-shot `migrate` service inside `up`. It exits 0 and
# is not part of the health gate below, which watches only the long-lived apps.
echo ">> waiting for the apps to report healthy..."
DEADLINE=$((SECONDS + 300))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  unhealthy=$("${COMPOSE[@]}" ps --format '{{.Name}} {{.Status}}' \
    | grep -E 'dw-(api|worker|web)-1' | grep -v healthy || true)
  if [ -z "$unhealthy" ]; then
    echo ">> all healthy:"
    "${COMPOSE[@]}" ps --format '{{.Name}}\t{{.Status}}' | grep -E 'dw-(api|worker|web)-1'
    exit 0
  fi
  sleep 5
done

echo ">> TIMED OUT. Still unhealthy:" >&2
echo "$unhealthy" >&2
"${COMPOSE[@]}" logs --no-color --tail 120 api worker web migrate >&2 || true
exit 1
