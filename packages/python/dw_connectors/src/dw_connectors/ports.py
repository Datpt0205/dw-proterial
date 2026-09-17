"""Connector ports implemented by provider adapters and the mock."""

from __future__ import annotations

from typing import Protocol

from dw_connectors.contracts import CreateExternalTask, ExternalTaskRef


class TaskConnectorPort(Protocol):
    """Creates tasks in an external work-management system.

    Implementations MUST be idempotent on ``idempotency_key``: retrying the
    same key returns the original reference and never creates a duplicate.
    """

    @property
    def connector_name(self) -> str: ...

    async def create_task(
        self,
        command: CreateExternalTask,
        idempotency_key: str,
    ) -> ExternalTaskRef: ...


class ChatSenderPort(Protocol):
    """Sends one plain-text message into a conversation.

    Deliberately the narrow intersection of every channel rather than the union:
    Slack takes blocks and a thread timestamp, Zalo takes neither, and a port
    carrying the richest provider's vocabulary would force every other adapter
    to explain what it cannot do. Code that needs a provider's own features
    takes that provider's client, and says so in its type.

    The id is whatever the channel calls a conversation - a Slack channel, a
    Zalo chat, a Teams thread. The return is the provider's message id, best
    effort, for code that later edits or deletes what it sent.
    """

    async def send_message(self, conversation_id: str, text: str) -> str: ...
