"""Slack as a ``ChatSenderPort``.

An anti-corruption layer, not a convenience wrapper. ``SlackChatClient`` speaks
Slack — keyword-only arguments, a channel, blocks, a thread timestamp — and code
that only needs "send this sentence to that conversation" should not have to
learn any of it, nor be rewritten when the channel becomes Zalo or Teams.
"""

from __future__ import annotations

from dataclasses import dataclass

from dw_connectors.adapters.slack_chat import SlackChatClient


@dataclass(frozen=True)
class SlackChatSender:
    """Implements ``ChatSenderPort`` over the full Slack client."""

    client: SlackChatClient

    async def send_message(self, conversation_id: str, text: str) -> str:
        return await self.client.post_message(channel=conversation_id, text=text)
