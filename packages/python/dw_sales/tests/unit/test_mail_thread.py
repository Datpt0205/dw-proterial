"""A customer conversation is a mail thread read from its headers, and the
cases hang off it (ticket 24, dw_sales ADR 0009 decisions 1-2).

The key a message is stored with (`thread_key`, `ThreadIndex`), and over the
in-memory world (`dw_sales.evals.world`, the services the API serves) a
thread holding three of Velatrix's POs: a reply naming one PO attaches to
that case only, a reply naming none is routed with the three offered and
Sales picks one, a reply from another customer joins nothing, and a case
shows the talk before its PO. The stored mailbox's own keys are
`tests/integration/test_sales_mailbox.py`'s.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import InterpretationPort, ModelUnavailableError
from dw_kernel.errors import ConflictError, PermissionDeniedError
from dw_platform.domain.messages import EmailAddress, InboundMessage
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR
from dw_sales.application.ports import SalesScope
from dw_sales.application.threads import (
    KeyedMessage,
    ThreadIndex,
    ThreadLinks,
    thread_key,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.evals.graders import AN, CALLERS, READER
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, SampleWith, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
VLX = "an.trinh@velatrix.example"
QRL = "ivy.tran@quorilo.example"
DAY = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)
PASS = {"spf": "pass", "dkim": "pass", "dmarc": "pass"}


def _id(name: str) -> str:
    return f"<{name}@mail.velatrix.example>"


def _mail(
    message_id: str,
    minutes: int,
    *,
    references: Sequence[str] = (),
    po: str | None = None,
    body: str = "Cảm ơn anh chị.",
    sender: str = VLX,
) -> dict[str, Any]:
    """A message of the thread: ``po`` names a fixture PO file it carries."""
    spec: dict[str, Any] = {
        "message_id": message_id,
        "sender": sender,
        "subject": f"Re: {message_id}",
        "received_at": (DAY + timedelta(minutes=minutes)).isoformat(),
        "body": body,
        "authentication": PASS,
        "internet_message_id": _id(message_id.lower()),
        "references": list(references),
    }
    if po is not None:
        spec["attachments"] = [
            {
                "attachment_id": f"{message_id}-A1",
                "name": po,
                "media_type": "application/octet-stream",
                "file": ATTACHMENTS_DIR / po,
            }
        ]
    return spec


# T0 asks before any PO; T1, T2 and T3 each carry one of Velatrix's POs, each
# a reply in the one conversation; R1 names the second PO, R2 names none, R3
# names a PO of no case of the thread and another customer's PO; X0
# and X1 are another customer's mails naming the thread, X0 before any PO.
CHAIN = (_id("t3"), _id("t2"), _id("t1"), _id("t0"))
THREAD = [
    _mail("T0", 0, body="Bên em sắp đặt hàng cáp, gửi PO trong tuần."),
    _mail("X0", 5, references=CHAIN[3:], sender=QRL, body="Please quote us too."),
    _mail("T1", 10, references=CHAIN[3:], po="M21_VLX-PO-2609-0131.xlsx"),
    _mail("T2", 20, references=CHAIN[2:], po="M33_VLX-PO-2610-0004.xlsx"),
    _mail("T3", 30, references=CHAIN[1:], po="M44_VLX-PO-2610-0011.xlsx"),
    _mail("R1", 60, references=CHAIN, body="Nhờ xác nhận ngày giao PO VLX-PO-2610-0004."),
    _mail("R2", 70, references=CHAIN, body="Cảm ơn anh chị, đã nhận."),
    _mail(
        "R3",
        75,
        references=CHAIN,
        body="Nhờ xác nhận giao hàng PO VLX-PO-2609-0118 và QRL-PO-0926-12.",
    ),
    _mail("X1", 80, references=CHAIN, sender=QRL, body="Please see our PO."),
]
OPENING = ["T0", "T1", "T2", "T3"]


def _intent_says(*numbers: str) -> InterpretationPort:
    """The intent step answering ``numbers``; every other step unavailable."""
    off = Recorded(failure=ModelUnavailableError("not this step"))
    intent = Recorded(
        raw={"language": "vi", "referenced_number_spans": list(numbers), "kind": "reply_to_case"}
    )
    return ByPrompt(defaultdict(lambda: off, {"sales.message_intent": intent}))


@pytest.fixture
def sample() -> Iterator[Any]:
    with SampleWith(THREAD) as sample:
        yield sample


def _world(sample: Any, model: InterpretationPort | None = None) -> World:
    return open_world(REPO, sample, CALLERS, model=model)


async def _opened(world: World) -> dict[str, uuid.UUID]:
    """The thread's POs processed: each its own case, T0 routed with no case."""
    seen = await world.process_each(AN, OPENING)
    assert seen["T0"][0].kind == "routed_to_sales"
    cases = {}
    for message_id in OPENING[1:]:
        disposition, _ = seen[message_id]
        assert disposition.kind == "case_created", message_id
        assert disposition.case_id is not None
        cases[message_id] = disposition.case_id
    return cases


# ----------------------------------------------------------------- the key --


def _message(name: str, minutes: int, *references: str) -> InboundMessage:
    return InboundMessage(
        message_id=name,
        sender=EmailAddress(address=VLX),
        subject=name,
        received_at=DAY + timedelta(minutes=minutes),
        body_text="",
        internet_message_id=_id(name.lower()),
        references=tuple(_id(r) for r in references),
    )


def test_a_message_takes_the_key_of_the_earliest_stored_message_it_names() -> None:
    reply = _message("C", 30, "b", "a")
    named = [
        KeyedMessage("B", DAY + timedelta(minutes=20), "key-b"),
        KeyedMessage("A", DAY + timedelta(minutes=10), "key-a"),
    ]

    assert thread_key(reply, named) == "key-a"
    assert thread_key(reply, []) == _id("c")
    bare = reply.model_copy(update={"internet_message_id": None})
    assert thread_key(bare, []) == "C"


def test_a_message_naming_two_threads_joins_the_earliest_and_no_key_changes() -> None:
    """Acceptance 4: A and B start two threads; C names both and joins A's,
    the earlier; A's and B's keys stay as they were stored."""
    a, b = _message("A", 0), _message("B", 10)
    index = ThreadIndex([a, b])
    before = (index.key("A"), index.key("B"))

    index.add(_message("C", 20, "b", "a"))

    assert index.key("C") == index.key("A") == _id("a")
    assert (index.key("A"), index.key("B")) == before == (_id("a"), _id("b"))
    assert [m.message_id for m in index.thread_of(a)] == ["A", "C"]


def test_a_reply_stored_before_what_it_answers_still_reaches_it() -> None:
    """Out of order: C (answering B and A) is stored first, then A and B. A
    keeps its own key, and C's thread is read by its key and by the keys of
    the messages it names, so it reaches both."""
    c = _message("C", 20, "b", "a")
    index = ThreadIndex([c, _message("A", 0), _message("B", 10, "a")])

    assert index.key("C") == _id("c")
    assert index.key("A") == index.key("B") == _id("a")
    assert [m.message_id for m in index.thread_of(c)] == ["A", "B", "C"]


class _Counted:
    """A mailbox that answers a thread and counts it, and refuses to be
    listed: the thread step never reads the whole mailbox."""

    def __init__(self, messages: list[InboundMessage]) -> None:
        self.index, self.threads = ThreadIndex(messages), 0

    async def list_messages(self, scope: SalesScope) -> list[InboundMessage]:
        raise AssertionError("the whole mailbox was listed for one message")

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        raise NotImplementedError("not exercised by the thread step")

    async def thread_messages(
        self, scope: SalesScope, message: InboundMessage
    ) -> list[InboundMessage]:
        self.threads += 1
        return self.index.thread_of(message)


async def test_a_reply_reads_its_own_thread_once_and_never_the_mailbox(sample: Any) -> None:
    world = _world(sample)
    await _opened(world)
    stored = [await world.inbox.get_message(ALPHA, m) for m in OPENING]
    reply = await world.inbox.get_message(ALPHA, "R2")
    assert reply is not None and all(stored)
    mailbox = _Counted([m for m in stored if m is not None])
    vlx = (await world.catalog.customer_by_code(ALPHA, "VLX")).data

    cases = await ThreadLinks(world.store, mailbox).cases(ALPHA, reply, vlx)

    assert len(cases) == 3 and mailbox.threads == 1


# --------------------------------------------------------- the three cases --


async def test_a_reply_naming_one_po_attaches_to_that_case_only(sample: Any) -> None:
    """Acceptance 1: the model reads the number, code resolves it against
    Velatrix's cases, and the reply joins T2's case alone."""
    world = _world(sample, _intent_says("VLX-PO-2610-0004"))
    cases = await _opened(world)

    ((disposition, _),) = (await world.process_each(AN, ["R1"])).values()

    assert disposition.kind == "attached_to_case"
    assert (disposition.case_kind, disposition.case_id) == (CaseKind.ORDER, cases["T2"])
    assert disposition.reply is not None and disposition.reply.linked_to == "T2"
    assert disposition.reading is not None and disposition.reading.references[0].order_case_id
    assert disposition.thread_cases == []


async def test_a_reply_naming_no_case_is_routed_with_the_three_offered(sample: Any) -> None:
    """Acceptance 2, with the model and without: naming none, Sales picks."""
    for model in (None, _intent_says()):
        world = _world(sample, model)
        cases = await _opened(world)

        ((disposition, _),) = (await world.process_each(AN, ["R2"])).values()

        assert (disposition.kind, disposition.reason) == ("routed_to_sales", "reply_to_case")
        assert disposition.case_id is None and disposition.reply is None
        # The inbox offers them by the number each goes by ("Chọn hồ sơ").
        (shown,) = [
            m for m in await world.services.inbox.messages(AN.context()) if m.message_id == "R2"
        ]
        offered = {c.case_id: c.number for c in shown.disposition.thread_cases}
        assert offered == {
            cases["T1"]: "VLX-PO-2609-0131",
            cases["T2"]: "VLX-PO-2610-0004",
            cases["T3"]: "VLX-PO-2610-0011",
        }


async def test_sales_picks_one_of_the_offered_cases_and_only_one_of_them(sample: Any) -> None:
    world = _world(sample)
    cases = await _opened(world)
    await world.process_each(AN, ["R2"])
    picks = world.services.routed_mail

    with pytest.raises(PermissionDeniedError):
        await picks.pick_case(READER.context(), "R2", cases["T3"])
    with pytest.raises(ConflictError) as refused:
        await picks.pick_case(AN.context(), "R2", uuid.UUID(int=0x99))
    assert refused.value.details["rule"] == "case_not_offered"
    # A case of the workspace, but not one the thread offered.
    (other,) = (await world.process_each(AN, ["M01"])).values()
    assert other[0].case_id is not None
    with pytest.raises(ConflictError):
        await picks.pick_case(AN.context(), "R2", other[0].case_id)

    picked = await picks.pick_case(AN.context(), "R2", cases["T3"])

    assert (picked.kind, picked.case_id) == ("attached_to_case", cases["T3"])
    assert picked.reply is not None
    assert (picked.reply.linked_to, picked.reply.picked_by) == ("T3", AN.user_id)
    (audited,) = [
        e for e in world.store.state(ALPHA).audit if e.action == "sales.message.case_picked"
    ]
    assert (audited.resource_id, audited.actor_id.value) == ("R2", AN.user_id)
    assert audited.details == {"case_kind": "order", "case_id": str(cases["T3"])}
    view = await world.services.orders.get(AN.context(), cases["T3"])
    assert [r.message_id for r in view.replies] == ["R2"]
    assert view.replies[0].picked_by == AN.user_id
    # Picked once: it is on a case now, and is not picked again.
    with pytest.raises(ConflictError):
        await picks.pick_case(AN.context(), "R2", cases["T1"])


async def test_a_number_outside_the_thread_or_another_customers_chooses_nothing(
    sample: Any,
) -> None:
    """What the model reads is resolved by code against the thread's own
    cases: Velatrix's PO on no case of this thread (M01's), or Quorilo's PO
    (M06's), points at none of the three, so Sales still picks."""
    for number in ("VLX-PO-2609-0118", "QRL-PO-0926-12"):
        world = _world(sample, _intent_says(number))
        await world.process_each(AN, ["M01", "M06"])
        await _opened(world)

        ((disposition, _),) = (await world.process_each(AN, ["R3"])).values()

        assert (disposition.kind, disposition.reason) == ("routed_to_sales", "reply_to_case")
        assert disposition.case_id is None
        assert disposition.reading is not None
        resolved = [r.number for r in disposition.reading.references]
        # Velatrix's own number is resolved, Quorilo's is not, and neither
        # is one of the three this reply's thread offers.
        assert resolved == (["VLX-PO-2609-0118"] if number.startswith("VLX") else [])


async def test_another_customers_mail_naming_the_thread_joins_no_case(sample: Any) -> None:
    """Acceptance 3: Quorilo's mail names Velatrix's thread; headers are the
    sender's to write, so it is classified as any other mail."""
    world = _world(sample)
    await _opened(world)

    ((disposition, _),) = (await world.process_each(AN, ["X1"])).values()

    assert disposition.kind == "routed_to_sales" and disposition.reason != "reply_to_case"
    assert disposition.reply is None and disposition.thread_cases == []


# ----------------------------------------------------- the talk before it --


async def test_a_case_shows_the_talk_before_its_po_and_only_its_customers(
    sample: Any,
) -> None:
    world = _world(sample)
    cases = await _opened(world)
    await world.process_each(AN, ["X0"])

    first = await world.services.orders.get(AN.context(), cases["T1"])
    third = await world.services.orders.get(AN.context(), cases["T3"])

    assert [m.message_id for m in first.thread_before] == ["T0"]
    # T1 and T2 came before T3's PO, of its customer, T0 too; Quorilo's X0,
    # on the thread by the headers it wrote, never shows.
    assert [m.message_id for m in third.thread_before] == ["T0", "T1", "T2"]
