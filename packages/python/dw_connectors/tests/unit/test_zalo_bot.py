"""ZaloBotClient dialect quirks: single-object result, 408 idle timeout."""

from __future__ import annotations

import httpx
import pytest

from dw_connectors.adapters.zalo_bot import ZaloBotClient

pytestmark = pytest.mark.unit

TOKEN = "bot-test-token"


def _patch_client(monkeypatch, handler) -> None:
    real_init = httpx.AsyncClient.__init__

    def fake_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", fake_init)


async def test_get_updates_treats_408_timeout_as_empty(monkeypatch) -> None:
    # An idle long-poll ends 200-with-ok:false-408; that is the steady state,
    # not a failure, so the loop must see an empty batch rather than an error.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error_code": 408, "description": "timeout"})

    _patch_client(monkeypatch, handler)
    assert await ZaloBotClient(bot_token=TOKEN).get_updates(offset=0) == []


async def test_get_updates_normalises_single_object_result(monkeypatch) -> None:
    # Zalo returns result as one object, not a Telegram-style array.
    one = {"message": {"chat": {"id": "z1"}, "text": "hi"}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": one})

    _patch_client(monkeypatch, handler)
    assert await ZaloBotClient(bot_token=TOKEN).get_updates(offset=0) == [one]


async def test_get_updates_raises_on_non_408_failure(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": False, "error_code": 401, "description": "bad token"}
        )

    _patch_client(monkeypatch, handler)
    with pytest.raises(RuntimeError):
        await ZaloBotClient(bot_token=TOKEN).get_updates(offset=0)
