"""`scripts/warm_model.py` against a model server of its own, over real HTTP."""

from __future__ import annotations

import importlib.util
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
_SPEC = importlib.util.spec_from_file_location("warm_model", REPO / "scripts" / "warm_model.py")
assert _SPEC is not None and _SPEC.loader is not None
warm_model = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(warm_model)


class Server(ThreadingHTTPServer):
    """A model server: what it was asked, how many first calls it refuses."""

    seen: list[tuple[str, dict[str, Any]]]
    refuse: int
    loaded: list[dict[str, Any]] | None
    key: str | None


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_: object) -> None:
        pass

    def _send(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.server.key = self.headers.get("Authorization")
        self.server.seen.append((self.path, body))
        if self.server.refuse:
            self.server.refuse -= 1
            self._send(503, {})
            return
        self._send(200, {})

    def do_GET(self) -> None:
        if self.server.loaded is None:
            self._send(404, {})
        else:
            self._send(200, {"models": self.server.loaded})


@pytest.fixture
def server() -> Iterator[Server]:
    running = Server(("127.0.0.1", 0), Handler)
    running.seen, running.refuse, running.loaded, running.key = [], 0, None, None
    thread = threading.Thread(target=running.serve_forever, daemon=True)
    thread.start()
    yield running
    running.shutdown()
    running.server_close()


def _base(server: Server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/v1"


def _profile(tmp_path: Path) -> Path:
    path = tmp_path / "p.yaml"
    path.write_text(
        """
profile_id: p
structured_extraction: {provider: onprem, model: chat-a}
reasoning: {provider: onprem, model: chat-a}
embedding: {provider: onprem, model: embed-a}
budgets: {max_input_tokens_per_run: 1}
""",
        encoding="utf-8",
    )
    return path


def test_the_shipped_profile_names_what_it_warms() -> None:
    chat, embedding = warm_model.models(warm_model.PROFILE)
    assert chat and embedding


def test_each_model_gets_one_smallest_call(server: Server, tmp_path: Path) -> None:
    assert warm_model.warm(_base(server), "k", _profile(tmp_path), wait=5, allow_cpu=False)
    paths = [path for path, _ in server.seen]
    assert paths == ["/v1/chat/completions", "/v1/embeddings"]
    chat = server.seen[0][1]
    assert (chat["model"], chat["max_tokens"]) == ("chat-a", 1)
    # A thinking model would otherwise spend the one token thinking.
    assert chat["reasoning_effort"] == "none"
    assert server.key == "Bearer k"


def test_a_server_still_starting_is_waited_for(
    server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(warm_model, "RETRY_SECONDS", 0.01)
    server.refuse = 2
    assert warm_model.warm(_base(server), None, _profile(tmp_path), wait=5, allow_cpu=False)


def test_a_model_that_never_loads_is_a_failure(
    server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(warm_model, "RETRY_SECONDS", 0.01)
    server.refuse = 10_000
    assert not warm_model.warm(_base(server), None, _profile(tmp_path), wait=0.05, allow_cpu=False)


def test_a_model_held_on_cpu_is_a_failure_a_healthcheck_would_pass(
    server: Server, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server.loaded = [{"name": "chat-a", "size_vram": 0}, {"name": "embed-a", "size_vram": 9}]
    assert not warm_model.warm(_base(server), None, _profile(tmp_path), wait=5, allow_cpu=False)
    assert "chat-a" in capsys.readouterr().out
    assert warm_model.warm(_base(server), None, _profile(tmp_path), wait=5, allow_cpu=True)


def test_a_server_with_no_such_endpoint_says_nothing_about_the_gpu(
    server: Server, tmp_path: Path
) -> None:
    server.loaded = None
    assert warm_model.warm(_base(server), None, _profile(tmp_path), wait=5, allow_cpu=False)
