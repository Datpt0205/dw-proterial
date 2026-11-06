"""Load the on-premises model before anyone needs it.

The first call after a model server starts loads the model: 582 s for qwen and
68 s for bge-m3 from a Docker Desktop volume (infra/onprem/README.md,
2026-10-19), longer than a step's route timeout, so the first person of the
day gets "not understood" and a chat that says nothing for minutes. A health
check does not tell: `ollama list` answers while nothing is loaded.

    python scripts/warm_model.py                  # once, after `up`
    python scripts/warm_model.py --every 300      # and again whenever it drops

Every model the profile routes to gets the smallest call it can answer, chat
and embedding alike; the profile file owns which those are. Once is enough
while the server holds it (`OLLAMA_KEEP_ALIVE=-1`), but a host restart or a
crash of the server unloads it with nothing else noticing, which is what
`--every` is for: the on-prem overlay runs it as the `model-warm` service, so
a reboot at night is warm by morning.

On Ollama it also asks where the model landed. Its first GPU discovery can
time out and leave it serving on CPU behind a passing healthcheck, ten times
slower, so that is an exit code and a line in the log, not a hope.

Exit codes: 0 warm, 1 a model did not load, 2 not configured.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE = REPO_ROOT / "configs" / "models" / "onprem.yaml"
# A model loading from a slow disk takes this long, and answers nothing until
# it has: the longest load measured (582 s) with room to spare.
LOAD_SECONDS = 900
RETRY_SECONDS = 5
_CHAT_ROUTES = ("structured_extraction", "reasoning", "chat", "fallback")


def models(profile: Path) -> tuple[list[str], list[str]]:
    """The profile's chat models and its embedding models, each once."""
    routes: dict[str, Any] = yaml.safe_load(profile.read_text(encoding="utf-8"))
    chat = {routes[r]["model"] for r in _CHAT_ROUTES if r in routes}
    embedding = {routes["embedding"]["model"]} if "embedding" in routes else set()
    return sorted(chat), sorted(embedding)


def _post(url: str, key: str | None, body: dict[str, Any], timeout: float) -> None:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def warm_one(base: str, key: str | None, model: str, *, embedding: bool, timeout: float) -> float:
    """Seconds the smallest call on ``model`` took."""
    started = time.monotonic()
    if embedding:
        _post(f"{base}/embeddings", key, {"model": model, "input": "warm"}, timeout)
    else:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "ok"}],
            "max_tokens": 1,
            "reasoning_effort": "none",
        }
        _post(f"{base}/chat/completions", key, body, timeout)
    return time.monotonic() - started


def on_cpu(base: str, key: str | None) -> list[str]:
    """The models Ollama holds with nothing on the GPU. Any other server has
    no such endpoint, and says nothing here."""
    url = base.removesuffix("/v1") + "/api/ps"
    request = urllib.request.Request(url)
    if key:
        request.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            loaded = json.load(response).get("models", [])
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
    return [m["name"] for m in loaded if not m.get("size_vram")]


def warm(base: str, key: str | None, profile: Path, *, wait: float, allow_cpu: bool) -> bool:
    """Every model loaded, waiting up to ``wait`` for a server still starting."""
    chat, embedding = models(profile)
    deadline = time.monotonic() + wait
    ok = True
    for model, is_embedding in [(m, False) for m in chat] + [(m, True) for m in embedding]:
        while True:
            left = deadline - time.monotonic()
            try:
                seconds = warm_one(base, key, model, embedding=is_embedding, timeout=max(left, 1))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if left <= RETRY_SECONDS:
                    print(f"model {model}: not loaded ({type(exc).__name__})", flush=True)
                    ok = False
                    break
                time.sleep(RETRY_SECONDS)
                continue
            print(f"model {model}: ready, {seconds:.1f} s", flush=True)
            break
    cpu = on_cpu(base, key) if ok else []
    if cpu:
        print(f"model on CPU, not the GPU: {', '.join(cpu)}", flush=True)
    return ok and (allow_cpu or not cpu)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=os.environ.get("DW_ONPREM_MODEL_BASE_URL"))
    parser.add_argument("--profile", type=Path, default=PROFILE)
    parser.add_argument("--wait", type=float, default=LOAD_SECONDS, help="seconds to wait per pass")
    parser.add_argument("--every", type=float, help="keep going, warming every this many seconds")
    parser.add_argument(
        "--allow-cpu", action="store_true", help="a host with no GPU: CPU is not a failure"
    )
    args = parser.parse_args()
    if not args.base_url:
        print("DW_ONPREM_MODEL_BASE_URL is not set", file=sys.stderr)
        return 2
    base = args.base_url.rstrip("/")
    key = os.environ.get("DW_ONPREM_MODEL_API_KEY") or None
    while True:
        ok = warm(base, key, args.profile, wait=args.wait, allow_cpu=args.allow_cpu)
        if args.every is None:
            return 0 if ok else 1
        time.sleep(args.every)


if __name__ == "__main__":
    sys.exit(main())
