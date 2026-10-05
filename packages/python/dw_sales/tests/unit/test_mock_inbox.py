"""`MockInbox`: every message and attachment read back through `InboxPort`."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR, attachment_path
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.domain.messages import EmailAddress, InboundMessage

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
OTHER_TENANT = SalesScope(TenantId(uuid.UUID(int=9)), WorkspaceId(uuid.UUID(int=10)))
OTHER_WORKSPACE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=10)))


@pytest.fixture(scope="module")
def inbox() -> MockInbox:
    return MockInbox.load(SCOPE)


def test_the_mock_satisfies_the_port(inbox: MockInbox) -> None:
    # The check is mypy's: this assignment fails typecheck when a signature drifts.
    port: InboxPort = inbox
    assert port is inbox


async def test_messages_are_listed_oldest_first_by_instant(inbox: MockInbox) -> None:
    messages = await inbox.list_messages(SCOPE)

    assert len(messages) == 32
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

    listed = await MockInbox([next_day, hanoi, tokyo], {}, scope=SCOPE).list_messages(SCOPE)

    assert [m.message_id for m in listed] == ["TOKYO", "HANOI", "NEXT-DAY"]


@pytest.mark.parametrize("scope", [OTHER_TENANT, OTHER_WORKSPACE], ids=["tenant", "workspace"])
async def test_another_scope_sees_an_empty_mailbox(inbox: MockInbox, scope: SalesScope) -> None:
    """The mock stands in for one tenant's mailbox: another scope naming the
    demo's own message and attachment ids reads nothing."""
    assert await inbox.read_attachment(SCOPE, "M01", "M01-A1") is not None

    assert await inbox.list_messages(scope) == ()
    assert await inbox.get_message(scope, "M01") is None
    assert await inbox.read_attachment(scope, "M01", "M01-A1") is None


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
    assert read == 29


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
        MockInbox(messages, contents, scope=SCOPE)
    with pytest.raises(ValueError, match="no content"):
        MockInbox([first], {}, scope=SCOPE)


async def test_a_message_id_listed_twice_is_refused(inbox: MockInbox) -> None:
    """Otherwise the later message replaces the earlier and a PO disappears."""
    no_attachments = await inbox.get_message(SCOPE, "M11")
    assert no_attachments is not None

    with pytest.raises(ValueError, match="appears twice"):
        MockInbox([no_attachments, no_attachments], {}, scope=SCOPE)


async def test_message_ids_follow_the_order_they_are_read_in(inbox: MockInbox) -> None:
    """The README's tables read top to bottom in processing order."""
    ids = [m.message_id for m in await inbox.list_messages(SCOPE)]

    assert ids == sorted(ids, key=lambda mid: int(mid[1:]))


async def test_the_mail_systems_results_are_read_from_the_fixture(inbox: MockInbox) -> None:
    unverified = [
        m.message_id
        for m in await inbox.list_messages(SCOPE)
        if {m.authentication.spf, m.authentication.dkim, m.authentication.dmarc} != {"pass"}
    ]

    assert unverified == ["M19"]


def test_a_fixture_message_that_states_no_mail_results_is_refused(tmp_path: Path) -> None:
    """The message model defaults to unverified; a fixture must not lean on it."""
    (record,) = [
        m
        for m in json.loads((DATA_DIR / "inbox.json").read_text(encoding="utf-8"))
        if m["message_id"] == "M11"
    ]
    del record["authentication"]
    (tmp_path / "inbox.json").write_text(json.dumps([record]), encoding="utf-8")

    with pytest.raises(ValueError, match=r"inbox\.json\[0\].*authentication"):
        MockInbox.load(SCOPE, data_dir=tmp_path)
