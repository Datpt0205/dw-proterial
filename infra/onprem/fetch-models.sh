#!/usr/bin/env bash
# Fetch every model the on-premises stack serves, once, on a host that can
# reach the internet (infra/onprem/README.md). Nothing here runs at request
# time: after this, the stack calls nothing outside the machine.
#
#   1. bge-reranker-v2-m3 (GGUF, Q8_0) into infra/onprem/models/, pinned to one
#      Hugging Face commit and checked against its sha256: a file that differs
#      is deleted, not served.
#   2. qwen3.5:9b -> qwen3.5-9b-dw, and bge-m3:567m, into the `model-data`
#      volume, by the one-shot `model-init` service (stop `model` first).
#
# --export <dir> afterwards writes both to <dir> for a plant with no internet;
# --import <dir> on that plant's host loads them back.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
compose=(docker compose --env-file .env -f infra/compose/docker-compose.yml
  -f infra/compose/docker-compose.onprem.yml)
volume="${COMPOSE_PROJECT_NAME:-compose}_model-data"
models="$root/infra/onprem/models"

rerank_repo="gpustack/bge-reranker-v2-m3-GGUF"
rerank_commit="3093af03b1a635e67b084b1d8c03c5f5e020fd05"
rerank_file="bge-reranker-v2-m3-Q8_0.gguf"
rerank_sha256="a43c7c9b11a4c1517e5bf95151960e1621d1b72f7a493364b01e386cf1aaa1d3"

checksum() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$1" | cut -d' ' -f1; }

fetch_reranker() {
  mkdir -p "$models"
  local target="$models/$rerank_file"
  if [ -f "$target" ] && [ "$(checksum "$target")" = "$rerank_sha256" ]; then
    echo "reranker: present, checksum matches"
    return
  fi
  curl --fail --location --retry 3 -o "$target.part" \
    "https://huggingface.co/$rerank_repo/resolve/$rerank_commit/$rerank_file"
  if [ "$(checksum "$target.part")" != "$rerank_sha256" ]; then
    rm -f "$target.part"
    echo "reranker: checksum mismatch, file deleted" >&2
    exit 1
  fi
  mv "$target.part" "$target"
  echo "reranker: fetched and verified"
}

fetch_ollama_models() {
  "${compose[@]}" stop model >/dev/null 2>&1 || true
  "${compose[@]}" --profile onprem-init run --rm model-init
}

case "${1:-}" in
  --export)
    out="${2:?usage: $0 --export <dir>}"
    mkdir -p "$out"
    cp "$models/$rerank_file" "$out/"
    docker run --rm -v "$volume:/data:ro" -v "$(cd "$out" && pwd):/out" \
      alpine:3.20.10@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc \
      tar czf /out/ollama-models.tgz -C /data .
    echo "exported to $out"
    ;;
  --import)
    in="${2:?usage: $0 --import <dir>}"
    mkdir -p "$models"
    cp "$in/$rerank_file" "$models/"
    [ "$(checksum "$models/$rerank_file")" = "$rerank_sha256" ] \
      || { echo "reranker: checksum mismatch" >&2; exit 1; }
    docker volume create "$volume" >/dev/null
    docker run --rm -v "$volume:/data" -v "$(cd "$in" && pwd):/in:ro" \
      alpine:3.20.10@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc \
      tar xzf /in/ollama-models.tgz -C /data
    echo "imported into $volume and $models"
    ;;
  "")
    fetch_reranker
    fetch_ollama_models
    ;;
  *)
    echo "usage: $0 [--export <dir> | --import <dir>]" >&2
    exit 2
    ;;
esac
