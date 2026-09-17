"""Shared Zalo self-link flow: parse one bot update, act, reply.

The same ``/start <token>`` / ``/stop`` handling drives two callers — the API
webhook (when Zalo can POST in) and the worker's long-poll loop (when it cannot,
e.g. a CDN in front of the API blocks Zalo's requests). Both parse an identical
update shape and write the identical row, so the parse, the signed-token codec
and the branch on ``text`` live here once; each caller supplies only a
``ZaloLinkStore`` (who owns the ``external_identities`` write) and a bot to
reply through.
"""

from __future__ import annotations

import base64
import contextlib
import hmac
import struct
import time
import uuid
from hashlib import sha256
from typing import Any, Protocol

from dw_connectors.adapters.zalo_bot import ZaloBotClient

_TOKEN_TTL_SECONDS = 900  # a connect token is good for 15 minutes
_STOP_WORDS = frozenset({"/stop", "/huy", "/hủy", "stop", "huỷ", "hủy"})


# ---- signed connect token (compact: 16B uuid + 4B expiry + 8B sig) ----
def make_connect_token(user_id: uuid.UUID, secret: str) -> str:
    body = user_id.bytes + struct.pack(">I", int(time.time()) + _TOKEN_TTL_SECONDS)
    sig = hmac.new(secret.encode(), body, sha256).digest()[:8]
    return base64.urlsafe_b64encode(body + sig).decode().rstrip("=")


def verify_connect_token(token: str, secret: str) -> uuid.UUID | None:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        body, sig = raw[:20], raw[20:]
        expected = hmac.new(secret.encode(), body, sha256).digest()[:8]
        if not hmac.compare_digest(sig, expected):
            return None
        if time.time() > struct.unpack(">I", body[16:20])[0]:
            return None
        return uuid.UUID(bytes=body[:16])
    except (ValueError, struct.error):
        return None


class ZaloLinkStore(Protocol):
    """Owns the ``external_identities`` (provider ``zalo``) write — see
    ``dw_platform.adapters.persistence.zalo_link_repo``. Injected so this module
    stays free of any database dependency."""

    async def link(self, user_id: uuid.UUID, zalo_id: str) -> None: ...

    async def unlink_by_zalo(self, zalo_id: str) -> None: ...


def parse_update(update: dict[str, Any]) -> tuple[str, str]:
    """Return ``(zalo_id, text)`` from a bot update; either may be empty.

    Zalo wraps the message under ``result`` on the poll path and delivers it at
    the top level on the webhook path; the chat id is under ``chat`` (private
    chat) or ``from``. Both shapes are normalised here.
    """
    message = (update.get("result") or update).get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or message.get("from") or {}
    return str(chat.get("id") or ""), text


async def handle_update(
    update: dict[str, Any],
    *,
    link_secret: str,
    store: ZaloLinkStore,
    bot: ZaloBotClient | None,
) -> None:
    """Act on one update: ``/start <token>`` links, ``/stop`` unlinks."""
    zalo_id, text = parse_update(update)
    if not zalo_id or not text:
        return

    async def reply(msg: str) -> None:
        if bot is not None:
            with contextlib.suppress(RuntimeError):
                await bot.send_message(zalo_id, msg)

    if text.startswith("/start "):
        user_id = verify_connect_token(text.split(maxsplit=1)[1].strip(), link_secret)
        if user_id is None:
            await reply("Mã kết nối không hợp lệ / đã hết hạn. Bấm 'Kết nối Zalo' lại nhé.")
            return
        await store.link(user_id, zalo_id)
        await reply("✅ Đã kết nối! Sale Intelligence sẽ gửi thông báo qua đây. Gõ /stop để dừng.")
    elif text.lower() in _STOP_WORDS:
        await store.unlink_by_zalo(zalo_id)
        await reply("Đã dừng nhận thông báo Zalo. Bấm 'Kết nối Zalo' trong app để nhận lại.")
