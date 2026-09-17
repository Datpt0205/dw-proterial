"""The shared Zalo self-link flow: token codec + update handling."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from dw_connectors.adapters.zalo_bot import ZaloBotClient
from dw_connectors.adapters.zalo_link import (
    handle_update,
    make_connect_token,
    parse_update,
    verify_connect_token,
)

_SECRET = "s3cr3t-link-signing-key"
_USER = uuid.UUID("450fbfd4-307f-447b-ae14-389aeb2f84ab")
_ZALO_ID = "733245f6b0b959e700a8"


class _FakeStore:
    def __init__(self) -> None:
        self.linked: list[tuple[uuid.UUID, str]] = []
        self.unlinked: list[str] = []

    async def link(self, user_id: uuid.UUID, zalo_id: str) -> None:
        self.linked.append((user_id, zalo_id))

    async def unlink_by_zalo(self, zalo_id: str) -> None:
        self.unlinked.append(zalo_id)


@dataclass(frozen=True)
class _FakeBot(ZaloBotClient):
    """A real ``ZaloBotClient`` with the one call ``handle_update`` makes
    replaced — ``handle_update`` takes the client itself, not a narrower port."""

    bot_token: str = "fake-token"
    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_message(self, chat_id: str, text: str) -> str:
        self.sent.append((chat_id, text))
        return "mid"


def _start_update(token: str) -> dict[str, Any]:
    # The exact poll-path shape observed from getUpdates (result-wrapped).
    return {
        "result": {
            "message": {
                "chat": {"id": _ZALO_ID, "chat_type": "PRIVATE"},
                "text": f"/start {token}",
                "from": {"id": _ZALO_ID, "display_name": "Đạt"},
            },
            "event_name": "message.text.received",
        }
    }


# ---- token codec ----
def test_token_round_trips() -> None:
    token = make_connect_token(_USER, _SECRET)
    assert verify_connect_token(token, _SECRET) == _USER


def test_token_rejects_wrong_secret() -> None:
    token = make_connect_token(_USER, _SECRET)
    assert verify_connect_token(token, "different-secret") is None


def test_token_rejects_tampering() -> None:
    token = make_connect_token(_USER, _SECRET)
    tampered = ("A" if token[0] != "A" else "B") + token[1:]
    assert verify_connect_token(tampered, _SECRET) is None


def test_token_rejects_garbage() -> None:
    assert verify_connect_token("not-a-real-token", _SECRET) is None


# ---- parse (both delivery shapes) ----
def test_parse_webhook_shape_without_result_wrapper() -> None:
    flat = {"message": {"chat": {"id": _ZALO_ID}, "text": "hi"}}
    assert parse_update(flat) == (_ZALO_ID, "hi")


def test_parse_falls_back_to_from_when_no_chat() -> None:
    update = {"result": {"message": {"from": {"id": _ZALO_ID}, "text": "hi"}}}
    assert parse_update(update) == (_ZALO_ID, "hi")


# ---- handle_update ----
async def test_start_with_valid_token_links_and_confirms() -> None:
    store, bot = _FakeStore(), _FakeBot()
    token = make_connect_token(_USER, _SECRET)
    await handle_update(_start_update(token), link_secret=_SECRET, store=store, bot=bot)
    assert store.linked == [(_USER, _ZALO_ID)]
    assert bot.sent and "kết nối" in bot.sent[0][1].lower()


async def test_start_with_bad_token_does_not_link() -> None:
    store, bot = _FakeStore(), _FakeBot()
    await handle_update(_start_update("bogus"), link_secret=_SECRET, store=store, bot=bot)
    assert store.linked == []
    assert bot.sent and "hợp lệ" in bot.sent[0][1].lower()


async def test_stop_unlinks() -> None:
    store, bot = _FakeStore(), _FakeBot()
    update = {"result": {"message": {"chat": {"id": _ZALO_ID}, "text": "/stop"}}}
    await handle_update(update, link_secret=_SECRET, store=store, bot=bot)
    assert store.unlinked == [_ZALO_ID]
    assert store.linked == []


async def test_empty_message_is_noop() -> None:
    store, bot = _FakeStore(), _FakeBot()
    await handle_update({"result": {"message": {}}}, link_secret=_SECRET, store=store, bot=bot)
    assert store.linked == [] and store.unlinked == [] and bot.sent == []


async def test_unknown_text_does_nothing() -> None:
    store, bot = _FakeStore(), _FakeBot()
    update = {"result": {"message": {"chat": {"id": _ZALO_ID}, "text": "xin chào"}}}
    await handle_update(update, link_secret=_SECRET, store=store, bot=bot)
    assert store.linked == [] and store.unlinked == [] and bot.sent == []


async def test_link_works_without_a_bot() -> None:
    # A reply channel is optional; the link must still be written.
    store = _FakeStore()
    token = make_connect_token(_USER, _SECRET)
    await handle_update(_start_update(token), link_secret=_SECRET, store=store, bot=None)
    assert store.linked == [(_USER, _ZALO_ID)]
