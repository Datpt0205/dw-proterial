"""`MockInbox`: every message and attachment read back through `InboxPort`."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, attachment_path
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.domain.messages import EmailAddress, InboundMessage

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))


@pytest.fixture(scope="module")
def inbox() -> MockInbox:
    return MockInbox.load()


def test_the_mock_satisfies_the_port(inbox: MockInbox) -> None:
    # The check is mypy's: this assignment fails typecheck when a signature drifts.
    port: InboxPort = inbox
    assert port is inbox


async def test_messages_are_listed_oldest_first_by_instant(inbox: MockInbox) -> None:
    messages = await inbox.list_messages(SCOPE)

    assert len(messages) == 12
    instants = [m.received_at for m in messages]
    assert instants == sorted(instants)
    # The fixture mixes offsets (M02 is sent from +09:00). Its file order and
    # its clock order already agree with the instants, so the sorting itself
    # is proven by the test below, not by this one.
    assert {m.received_at.utcoffset() for m in messages} != {messages[0].received_at.utcoffset()}


async def test_messages_are_sorted_by_instant_whatever_order_they_arrive_in() -> None:
    """A duplicate or a revised PO is recognised by reading oldest first, so the
    order is the port's promise rather than a property of one fixture file."""

    def message(message_id: str, received_at: str) -> InboundMessage:
        return InboundMessage(
            message_id=message_id,
            sender=EmailAddress(address="scm@corvane-group.example"),
            subject=message_id,
            received_at=datetime.fromisoformat(received_at),
            body_text="",
        )

    # 10:00 in Tokyo is 08:00 in Hanoi: the earlier instant shows the later clock.
    tokyo = message("TOKYO", "2026-09-22T10:00:00+09:00")
    hanoi = message("HANOI", "2026-09-22T09:00:00+07:00")
    next_day = message("NEXT-DAY", "2026-09-23T08:00:00+07:00")

    listed = await MockInbox([next_day, hanoi, tokyo], {}).list_messages(SCOPE)

    assert [m.message_id for m in listed] == ["TOKYO", "HANOI", "NEXT-DAY"]


async def test_every_message_is_found_by_its_id(inbox: MockInbox) -> None:
    for message in await inbox.list_messages(SCOPE):
        assert await inbox.get_message(SCOPE, message.message_id) == message
    assert await inbox.get_message(SCOPE, "M99") is None


async def test_every_attachment_reads_back_as_the_file_its_digest_describes(
    inbox: MockInbox,
) -> None:
    read = 0
    for message in await inbox.list_messages(SCOPE):
        for attachment in message.attachments:
            content = await inbox.read_attachment(
                SCOPE, message.message_id, attachment.attachment_id
            )
            on_disk = attachment_path(ATTACHMENTS_DIR, message.message_id, attachment.name)

            assert content is not None
            assert content.attachment == attachment
            assert content.data == on_disk.read_bytes()
            assert attachment.size == len(content.data)
            assert attachment.sha256 == hashlib.sha256(content.data).hexdigest()
            read += 1
    assert read == 11


@pytest.mark.parametrize(
    ("message_id", "attachment_id"),
    [("M01", "M01-A9"), ("M99", "M01-A1"), ("M11", "M01-A1"), ("M02", "M01-A1")],
)
async def test_an_attachment_is_read_only_through_the_message_that_carries_it(
    inbox: MockInbox, message_id: str, attachment_id: str
) -> None:
    assert await inbox.read_attachment(SCOPE, message_id, attachment_id) is None


async def test_two_messages_may_carry_the_same_file_name_with_different_content(
    inbox: MockInbox,
) -> None:
    first = await inbox.get_message(SCOPE, "M01")
    resent = await inbox.get_message(SCOPE, "M08")

    assert first is not None
    assert resent is not None
    assert first.attachments[0].name == resent.attachments[0].name
    assert first.attachments[0].sha256 != resent.attachments[0].sha256


async def test_content_that_disagrees_with_its_description_is_refused_at_load(
    inbox: MockInbox,
) -> None:
    messages = await inbox.list_messages(SCOPE)
    first = messages[0]
    contents = {(m.message_id, a.attachment_id): b"" for m in messages for a in m.attachments}

    with pytest.raises(ValueError, match="M01-A1"):
        MockInbox(messages, contents)
    with pytest.raises(ValueError, match="no content"):
        MockInbox([first], {})


async def test_a_message_id_listed_twice_is_refused(inbox: MockInbox) -> None:
    """Otherwise the later message replaces the earlier and a PO disappears."""
    no_attachments = await inbox.get_message(SCOPE, "M11")
    assert no_attachments is not None

    with pytest.raises(ValueError, match="appears twice"):
        MockInbox([no_attachments, no_attachments], {})
