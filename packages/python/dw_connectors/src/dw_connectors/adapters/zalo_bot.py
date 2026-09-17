"""Zalo Bot Platform client (bot.zaloplatforms.com) — Telegram-style dialect.

Token rides in the URL; ``getUpdates`` long-polls (no public webhook needed
for local dev); ``sendMessage`` posts plain text. Responses wrap payloads in
{"ok": bool, "result": ..., "description": ...} exactly like Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_BASE = "https://bot-api.zaloplatforms.com"


@dataclass(frozen=True)
class ZaloBotClient:
    bot_token: str
    poll_timeout: int = 25

    async def get_updates(self, offset: int) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(
            base_url=f"{_BASE}/bot{self.bot_token}", timeout=self.poll_timeout + 10
        ) as client:
            response = await client.get(
                "/getUpdates",
                params={"offset": offset, "timeout": self.poll_timeout},
            )
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            # A long-poll that saw no message ends with 408 "Request timeout".
            # That is the idle steady state, not a failure — a caller looping on
            # getUpdates would otherwise crash on every quiet poll.
            if data.get("error_code") == 408:
                return []
            raise RuntimeError(f"zalo getUpdates failed: {data.get('description')}")
        # Zalo returns ``result`` as a single update object (not a Telegram-style
        # array). Normalise both shapes so callers always see a list.
        result = data.get("result")
        if result is None:
            return []
        return result if isinstance(result, list) else [result]

    async def send_message(self, chat_id: str, text: str) -> str:
        """Send plain text; returns the message id (best effort)."""
        async with httpx.AsyncClient(base_url=f"{_BASE}/bot{self.bot_token}", timeout=15) as client:
            response = await client.post("/sendMessage", json={"chat_id": chat_id, "text": text})
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"zalo sendMessage failed: {data.get('description')}")
        result = data.get("result") or {}
        return str(result.get("message_id", ""))

    async def set_webhook(self, url: str) -> None:
        """Point the bot at ``url`` so updates are POSTed there instead of polled."""
        async with httpx.AsyncClient(base_url=f"{_BASE}/bot{self.bot_token}", timeout=15) as client:
            response = await client.post("/setWebhook", json={"url": url})
            response.raise_for_status()
            data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"zalo setWebhook failed: {data.get('description')}")

    async def delete_webhook(self) -> None:
        """Remove the webhook so ``getUpdates`` long-polling works again."""
        async with httpx.AsyncClient(base_url=f"{_BASE}/bot{self.bot_token}", timeout=15) as client:
            response = await client.get("/deleteWebhook")
            response.raise_for_status()

    async def get_webhook_info(self) -> dict[str, Any]:
        """The current webhook target (empty ``url`` means none is set)."""
        async with httpx.AsyncClient(base_url=f"{_BASE}/bot{self.bot_token}", timeout=15) as client:
            response = await client.get("/getWebhookInfo")
            response.raise_for_status()
            data = response.json()
        return dict(data.get("result") or {})
