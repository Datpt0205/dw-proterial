"""A customer's notation learned from Sales' confirmations (ticket 37): code
learns it from the value Sales keeps against the words it was read from, and
every reader of that customer's words reads by it where a document says
nothing, never another customer's or another tenant's.

Over the in-memory world (`dw_sales.evals.world`) with the fictional mail and
the scripted answers the readers' own tests use. The table, its RLS and its
grants are `tests/integration/test_customer_notations_db.py`'s.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import DomainError, NotFoundError, PermissionDeniedError
from dw_platform.domain.notation import Learned
from dw_platform.domain.notation import notation_of as _notation_of
from dw_sales.adapters.mock import MockInbox
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.domain.customer_notation import NotationEntry, customer_record, lesson
from dw_sales.domain.handoffs import locate, quantity_at
from dw_sales.domain.orders import OrderCase, RegionFlag
from dw_sales.domain.quotes import QuoteFindingCode
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, SampleWith, World, open_world
from dw_sales.testing.customer_notations import MemoryCustomerNotations

from .test_handoffs import UNSETTLED
from .test_handoffs import _read as _read_handoff
from .test_po_body import VI, _point_priced
from .test_po_body import _model as _po_model
from .test_rfq_requests import M37, SCOPE, _Settled, _world_with
from .test_rfq_requests import _open as _open_rfq

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AT = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
COMMA = {"VLX": {"decimal_mark": ","}}


def _entries(world: World, customer: str = "VLX") -> list[NotationEntry]:
    return [e for key, e in world.notations.rows.items() if key[:3] == (*_alpha(), customer)]


def _alpha() -> tuple[object, object]:
    return (ALPHA.tenant_id.value, ALPHA.workspace_id.value)


# ----------------------------------------------------------- the lesson --


@pytest.mark.parametrize(
    ("written", "kept", "learned"),
    [
        ("1.200 m", Decimal(1200), Learned("decimal_mark", ",")),
        ("1,200 m", Decimal(1200), Learned("decimal_mark", ".")),
        ("SL 1.200", Decimal("1.2"), Learned("decimal_mark", ".")),
        ("05/11/2026", date(2026, 11, 5), Learned("date_order", "day_first")),
        ("05/11", date(2026, 5, 11), Learned("date_order", "month_first")),
        # Words that read by themselves, or a value neither reading gives.
        ("1200 m", Decimal(1200), None),
        ("1.200 m", Decimal(1500), None),
        ("25/11/2026", date(2026, 11, 25), None),
        ("2.000 m x 3", Decimal(2000), None),
    ],
)
def test_a_value_kept_teaches_only_the_one_reading_that_gives_it(
    written: str, kept: object, learned: Learned | None
) -> None:
    found = lesson("quantity", written, kept)
    assert (found.learned if found else None) == learned


def test_an_entry_names_what_settled_it_or_that_a_person_set_it() -> None:
    base: dict[str, Any] = {"customer_code": "VLX", "kind": "decimal_mark", "by": AN.user_id}
    with pytest.raises(ValueError, match="names the value"):
        NotationEntry.model_validate({**base, "value": ",", "source": "confirmed", "at": AT})
    with pytest.raises(ValueError, match="names no case"):
        NotationEntry.model_validate(
            {**base, "value": ",", "source": "set", "at": AT, "field": "quantity"}
        )
    with pytest.raises(ValueError, match="holds no such value"):
        NotationEntry.model_validate({**base, "value": "USD", "source": "set", "at": AT})


# ------------------------------------------------- a request (quotation) --


async def test_a_quantity_left_open_is_anchored_at_its_words_for_sales() -> None:
    case = await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE))

    first, second = case.request.document.items
    assert first.unsettled == second.unsettled == ("quantity",)
    assert (first.quantity.source.quote, second.quantity.source.quote) == ("1.200 m", "3.000 m")


async def test_sales_typing_the_quantity_teaches_the_customers_decimal_mark() -> None:
    world, case_id = _world_with(await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE)))

    await world.services.quote_commands.answer_finding(
        AN.context(),
        case_id,
        "rfq_incomplete:1",
        case_version=world.quote(case_id).case_version,
        quantity=Decimal(1200),
    )

    (entry,) = _entries(world)
    assert (entry.kind, entry.value, entry.source) == ("decimal_mark", ",", "confirmed")
    assert (entry.case_kind, entry.case_id, entry.field) == ("quote", case_id, "quantity")
    assert (entry.written, entry.confirmed, entry.by) == ("1.200 m", "1200", AN.user_id)
    (event,) = world.notations.events
    assert event.action == "sales.customer_notation.learned"
    # The audit names the kind and the case, never the customer's words.
    assert "1.200" not in json.dumps(event.details)
    # Another tenant holds nothing of it.
    assert await world.notations.entries(BETA, "VLX") == []


async def test_a_value_typed_that_neither_reading_gives_teaches_nothing() -> None:
    world, case_id = _world_with(await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE)))

    await world.services.quote_commands.answer_finding(
        AN.context(),
        case_id,
        "rfq_incomplete:1",
        case_version=world.quote(case_id).case_version,
        quantity=Decimal(1500),
    )

    assert _entries(world) == [] and world.notations.events == []


async def test_a_confirmation_of_what_is_known_writes_nothing_again() -> None:
    records = MemoryCustomerNotations.seeded(SCOPE, COMMA)
    world, case_id = _world_with(
        await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE), records=records)
    )
    world.notations.rows.update(MemoryCustomerNotations.seeded(ALPHA, COMMA).rows)
    entry = _entries(world)[0]
    await world.services.sources.quote_message_text(AN.context(), case_id)

    await world.services.quote_commands.answer_finding(
        AN.context(),
        case_id,
        "value_uncertain:1",
        case_version=world.quote(case_id).case_version,
        field="quantity",
        value="1200",
    )

    # Learned as "," again from a value the record read: no new entry, but
    # the evidence becomes the confirmation's once (a person had set it).
    (now,) = _entries(world)
    assert (now.value, now.source, now.written) == (",", "confirmed", "1.200 m")
    assert entry.source == "set"


async def test_acceptance_1_the_next_request_is_read_by_the_record_and_flagged() -> None:
    """Velatrix's "1.200 m" confirmed as 1200 m: its next "1.200 m" and
    "3.000 m" read as 1200 and 3000 m, each flagged as settled by the record
    beside `model_read`, so Sales still confirms each."""
    records = MemoryCustomerNotations.seeded(SCOPE, COMMA)

    case = await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE), records=records)

    first, second = case.request.document.items
    assert (first.quantity.value, second.quantity.value) == (Decimal(1200), Decimal(3000))
    for item in (first, second):
        flags = {(f.field, f.flag) for f in item.flags}
        assert ("quantity", RegionFlag.NOTATION_FROM_RECORD) in flags
        assert ("quantity", RegionFlag.MODEL_READ) in flags
        assert item.unsettled == ()
        # A date the request settles by itself is not the record's.
        assert ("needed_by", RegionFlag.NOTATION_FROM_RECORD) not in flags
    uncertain = {f.line_no: f.flagged for f in case.findings}
    assert "quantity" in uncertain[1]
    assert not any(f.code is QuoteFindingCode.RFQ_INCOMPLETE for f in case.findings)


@pytest.mark.parametrize(
    "records",
    [
        # Acceptance 2: another customer's record settles nothing of Velatrix's.
        MemoryCustomerNotations.seeded(SCOPE, {"NRV": {"decimal_mark": ","}}),
        # Nor does Velatrix's own code in another tenant.
        MemoryCustomerNotations.seeded(BETA, COMMA),
    ],
    ids=["another_customer", "another_tenant"],
)
async def test_acceptance_2_no_other_record_settles_this_customers_request(
    records: MemoryCustomerNotations,
) -> None:
    case = await _open_rfq("M37", M37, inbox=MockInbox.load(SCOPE), records=records)

    first, second = case.request.document.items
    assert (first.quantity.value, second.quantity.value) == (None, None)
    assert first.unsettled == second.unsettled == ("quantity",)


async def test_a_request_that_contradicts_the_record_goes_to_a_person() -> None:
    # M37 with a price "0,42": the mail itself says its decimal mark is a
    # comma; a record saying point is contradicted, and nothing is read.
    records = MemoryCustomerNotations.seeded(SCOPE, {"VLX": {"decimal_mark": "."}})

    case = await _open_rfq("M37", M37, inbox=_Settled(), records=records)

    first, second = case.request.document.items
    assert (first.quantity.value, second.quantity.value) == (None, None)
    assert case.request.reading is not None
    assert case.request.reading.refused["quantity_contradicts_record"] == 2


# ----------------------------------------------------------- a PO (order) --


def _second_po(spec: dict[str, Any]) -> dict[str, Any]:
    """The same customer's next PO, written with a decimal point in its prices,
    so nothing in it says how "6.100 m" groups."""
    text = json.dumps(_point_priced(spec), ensure_ascii=False)
    renamed = text.replace("VLX-PO-2610-0201", "VLX-PO-2610-0202")
    pointed: dict[str, Any] = json.loads(renamed)
    pointed["message"]["message_id"] = "M-NOTATION-2"
    return pointed


@dataclass
class _InTurn:
    """The PO reader's answers, one per mail in the order they are read."""

    answers: list[dict[str, Any]]
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        return await Recorded(raw=self.answers.pop(0)).interpret(prompt, inputs, schema, **kwargs)


async def test_acceptance_1_a_po_quantity_confirmed_settles_the_next_po() -> None:
    later = _second_po(VI)
    model = ByPrompt(
        {
            "sales.message_intent": _po_model(None).models["sales.message_intent"],
            PO_BODY_EXTRACTION.prompt_id: _InTurn([VI["answer"], later["answer"]]),
        }
    )
    with SampleWith([VI["message"], later["message"]]) as sample:
        world = open_world(REPO, sample, CALLERS, model=model)
        first_id = VI["message"]["message_id"]
        _, first = (await world.process_each(AN, [first_id]))[first_id]
        assert isinstance(first, OrderCase)
        # Sales keeps line 1's "6.100 m" as 6100 m (the PO's own "0,0420" read it).
        await world.services.order_commands.correct_value(
            AN.context(),
            first.case_id,
            "value_uncertain:1",
            case_version=world.order(first.case_id).case_version,
            field="quantity",
            value="6100",
        )
        (entry,) = _entries(world)
        assert (entry.value, entry.case_kind, entry.field) == (",", "order", "quantity")
        assert entry.written == "6.100 m" and entry.confirmed == "6100"

        _, second = (await world.process_each(AN, ["M-NOTATION-2"]))["M-NOTATION-2"]

    assert isinstance(second, OrderCase)
    line = second.line(1).po_line
    assert line.quantity == Decimal(6100)
    assert {(f.field, f.flag) for f in line.flags} >= {
        ("quantity", RegionFlag.NOTATION_FROM_RECORD),
        ("quantity", RegionFlag.MODEL_READ),
    }


async def test_without_a_record_the_next_po_is_left_to_a_person() -> None:
    later = _second_po(VI)
    with SampleWith([later["message"]]) as sample:
        world = open_world(REPO, sample, CALLERS, model=_po_model(later["answer"]))
        _, case = (await world.process_each(AN, ["M-NOTATION-2"]))["M-NOTATION-2"]
    assert case is None


# -------------------------------------------------------------- hand-off --


def test_a_hand_off_quantity_is_settled_by_the_customers_record_alone() -> None:
    text = "Dòng 1: giảm còn 2.000 m"
    located = locate(text, "2.000 m", bounded=True)
    assert located is not None
    own = _notation_of(text)

    alone = quantity_at(text, located, own)
    with_record = quantity_at(text, located, own, customer_record(_set("VLX", ",")))

    assert alone is not None and alone.value is None and not alone.by_record
    assert with_record is not None and with_record.value == Decimal(2000)
    assert with_record.by_record


def _set(customer: str, value: str) -> list[NotationEntry]:
    return [
        NotationEntry(
            customer_code=customer,
            kind="decimal_mark",
            value=value,
            source="set",
            by=AN.user_id,
            at=AT,
        )
    ]


# ------------------------------------------------- the master data screen --


async def test_a_person_sets_reads_and_forgets_a_customers_notation() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    service = world.services.customer_notations

    view = await service.set(AN.context(), "VLX", "date_order", "day_first")

    (entry,) = view.entries
    assert (entry.kind, entry.value, entry.source, entry.case_id) == (
        "date_order",
        "day_first",
        "set",
        None,
    )
    assert (await service.entries(READER.context(), "VLX")).entries == view.entries
    assert [e.action for e in world.notations.events] == ["sales.customer_notation.set"]
    gone = await service.forget(AN.context(), "VLX", "date_order")
    assert gone.entries == []
    assert world.notations.events[-1].action == "sales.customer_notation.forgotten"


async def test_the_screen_refuses_what_a_caller_may_not_do() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    service = world.services.customer_notations

    # Reading is not changing: a reader may not set or forget one.
    with pytest.raises(PermissionDeniedError):
        await service.set(READER.context(), "VLX", "decimal_mark", ",")
    with pytest.raises(PermissionDeniedError):
        await service.forget(READER.context(), "VLX", "decimal_mark")
    # A value the kind does not hold, a customer the workspace has not.
    with pytest.raises(DomainError):
        await service.set(AN.context(), "VLX", "decimal_mark", ";")
    with pytest.raises(NotFoundError):
        await service.set(AN.context(), "ZZZ", "decimal_mark", ",")
    with pytest.raises(NotFoundError):
        await service.forget(AN.context(), "VLX", "decimal_mark")
    assert world.notations.events == []


async def test_another_tenant_neither_reads_nor_changes_this_tenants_notation() -> None:
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS)
    service = world.services.customer_notations
    await service.set(AN.context(), "VLX", "decimal_mark", ",")

    # Velatrix is no customer of tenant beta: refused before anything is read.
    with pytest.raises(NotFoundError):
        await service.entries(OUTSIDER.context(BETA), "VLX")
    with pytest.raises(NotFoundError):
        await service.forget(OUTSIDER.context(BETA), "VLX", "decimal_mark")
    assert len(_entries(world)) == 1
    assert await world.notations.entries(BETA, "VLX") == []


def test_the_record_is_the_customers_entries() -> None:
    record = customer_record(_set("VLX", ","))
    assert record.decimal_mark == ","
    assert customer_record([]).decimal_mark is None
    assert uuid.UUID(int=0xA1) == AN.user_id


_UNSETTLED_CHANGE = {
    "po_no_span": "VLX-PO-2608-0102",
    "lines": [
        {"line_or_item_span": "2", "new_quantity_span": "2.000 m", "new_date_span": None},
        {"line_or_item_span": "VX-C4B22", "new_quantity_span": None, "new_date_span": "05/12/2026"},
    ],
}


async def test_a_hand_off_reads_what_the_mail_leaves_open_by_the_senders_record() -> None:
    records = MemoryCustomerNotations.seeded(
        ALPHA, {"VLX": {"decimal_mark": ",", "date_order": "day_first"}}
    )

    handoff = await _read_handoff(_UNSETTLED_CHANGE, UNSETTLED, records=records)

    by_line = {line.line_no: line for line in handoff.lines}
    assert (by_line[2].new_quantity, by_line[2].from_record) == (Decimal(2000), ("quantity",))
    assert (by_line[1].new_date, by_line[1].from_record) == (date(2026, 12, 5), ("date",))
    assert handoff.refused == {}


@pytest.mark.parametrize(
    "records",
    [
        MemoryCustomerNotations.seeded(ALPHA, {"NRV": {"decimal_mark": ","}}),
        MemoryCustomerNotations.seeded(BETA, {"VLX": {"decimal_mark": ","}}),
    ],
    ids=["another_customer", "another_tenant"],
)
async def test_a_hand_off_reads_no_other_customers_or_tenants_record(
    records: MemoryCustomerNotations,
) -> None:
    handoff = await _read_handoff(_UNSETTLED_CHANGE, UNSETTLED, records=records)

    by_line = {line.line_no: line for line in handoff.lines}
    assert by_line[2].new_quantity is None and by_line[2].from_record == ()
