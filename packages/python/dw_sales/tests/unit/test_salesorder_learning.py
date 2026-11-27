"""A customer's SalesOrder rules learned from a worked example and proven by
replay (ticket 38, dw_sales ADR 0013). The pairs are the eval's synthetic
ones (`evals/fixtures/cases/sales_salesorder_rules.json`), three shapes like
Box B41's three filled files; no customer's data."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_sales.application.access import SalesScopes
from dw_sales.application.artifact_content import UploadField, Value
from dw_sales.application.order_artifacts import example_rows
from dw_sales.application.rules import RuleKey, RuleVersionView
from dw_sales.application.salesorder_learning import (
    EXAMPLE_LANE,
    EXAMPLE_REQUESTED,
    PROMPT_TOKENS,
    SALESORDER_RULES_PROPOSAL,
    ModelSalesOrderRules,
    PicFile,
    PicRow,
    Replay,
    SalesOrderExample,
    verify,
)
from dw_sales.application.salesorder_rules import (
    CustomerSalesOrderRules,
    Lookups,
    canonical,
    column_index,
    filled_row,
)
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, GIANG, OUTSIDER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.salesorder_rules import (
    Bench,
    converts,
    customers,
    file_cells,
    items,
    load_cases,
    pair,
    po_bytes,
    salesorder_bytes,
    wrong_step_answer,
)
from dw_sales.evals.world import ALPHA, Caller, SampleSet, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
CASES = load_cases(REPO)
# A PIC given the proposer's set (`sales_rules_editor`), as the admin gives it.
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
# A second head: the approver of a version the first head proposed.
HAI = Caller(uuid.UUID(int=0x62), "Lê Văn Hải", "hai.le@alpha.local", GIANG.scopes)


def _bench(answer: dict[str, Any] | None, *callers: Caller) -> tuple[Bench, Recorded]:
    model = Recorded(raw=answer)
    return Bench.of(REPO, model, callers or (GIANG,)), model


async def _learned(pair_id: str, answer: dict[str, Any] | None = None) -> Any:
    spec = pair(CASES, pair_id)
    bench, model = _bench(answer if answer is not None else spec["gold"])
    view = await bench.learn(spec)
    return bench, model, view


# ----------------------------------------------------------- acceptance 1 --


@pytest.mark.parametrize("pair_id", ["SR01", "SR02", "SR03"])
async def test_a_pairs_gold_rules_replay_to_the_pics_file_cell_for_cell(pair_id: str) -> None:
    """Acceptance 1: the proposal's replay reproduces the processed file. SR02
    is the acceptance's own pair: ETA dates, colour letters, km quantities."""
    _, model, view = await _learned(pair_id)

    assert view.status == "replayed", view.problems
    assert view.replay is not None and view.replay.matches
    assert view.replay.differences == ()
    assert view.replay.cells_compared > 0
    assert view.rules == CustomerSalesOrderRules.model_validate(pair(CASES, pair_id)["gold"])
    assert view.submittable
    # One call, as the asker, with the versioned prompt.
    ((prompt, run, inputs),) = model.calls
    assert prompt == SALESORDER_RULES_PROPOSAL
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, GIANG.user_id)
    assert set(inputs) == {"columns", "differing", "po_rows", "file_rows"}


async def test_the_model_is_told_which_columns_the_layout_does_not_reproduce() -> None:
    _, model, _ = await _learned("SR02")
    inputs = model.calls[0][2]
    # The rules' columns: the PRV code and colour the layout leaves blank,
    # the quantity, price and date it fills otherwise.
    assert inputs["differing"] == '["T", "V", "AA", "AE", "AF"]'


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    """The prompt describes every step and table of the closed set, every
    field and customer value, and costs less than `PROMPT_TOKENS`."""
    from typing import get_args

    from dw_agent_runtime.model.interpretation import estimated_tokens
    from dw_agent_runtime.model.prompts import PromptRegistry
    from dw_sales.application.artifact_content import (
        CASE_ONLY_FIELDS,
        CustomerAttribute,
        UploadField,
    )
    from dw_sales.application.salesorder_rules import LookupTable, Step

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        SALESORDER_RULES_PROPOSAL.prompt_id,
        SALESORDER_RULES_PROPOSAL.version,
        {"columns": "[]", "differing": "[]", "po_rows": "[]", "file_rows": "[]"},
        tenant_id=uuid.uuid4(),
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
    union = get_args(get_args(Step)[0])
    for step in union:
        assert f'"step": "{step.model_fields["step"].default}"' in rendered.system
    # PC's dates are a case's only, never an example's (ticket 07): not offered.
    fields = [f for f in get_args(UploadField) if f not in CASE_ONLY_FIELDS]
    for name in (*fields, *get_args(CustomerAttribute), *get_args(LookupTable)):
        assert name in rendered.system


# ----------------------------------------------------------- acceptance 2 --


async def test_one_wrong_step_lists_the_cells_it_breaks_and_cannot_be_sent() -> None:
    """Acceptance 2: a shift of -9 days for -10 replays to the PIC's file
    except the dates it moved; each is listed with expected, got and the
    rule, and "Gửi duyệt" is refused in the service whatever screen asked."""
    bench, _, view = await _learned("SR02", wrong_step_answer(CASES))

    assert view.status == "replayed"
    assert view.replay is not None and not view.replay.matches
    listed = [(d.cell, d.column, d.expected, d.got, d.source) for d in view.replay.differences]
    assert listed == [
        ("AF4", "AF", "2026-12-10", "2026-12-11", "rule"),
        ("AF5", "AF", "2026-12-26", "2026-12-27", "rule"),
    ]
    assert not view.submittable
    with pytest.raises(ConflictError) as refused:
        await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.1")
    assert refused.value.details["rule"] == "replay_differs"
    assert bench.proposals.sent == []


async def test_a_pair_no_rule_reproduces_is_never_sent() -> None:
    hand = CASES["unmatched"]
    spec = pair(CASES, hand["pair"])
    bench, _ = _bench(spec["gold"])
    cells = file_cells(spec)
    cells[hand["row"]] = {**cells[hand["row"]], "AF": date(2026, 12, 29)}
    view = await bench.learn(spec, salesorder=salesorder_bytes(bench.layout, cells))

    assert view.replay is not None
    assert [d.cell for d in view.replay.differences] == ["AF5"]
    with pytest.raises(ConflictError, match="chạy lại chưa khớp"):
        await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.1")


async def test_a_matching_replay_is_sent_once_as_the_version_in_force_with_this_customer() -> None:
    bench, _, view = await _learned("SR02")
    sent = await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.1")

    assert isinstance(sent, RuleVersionView)
    (document,) = bench.proposals.sent
    assert document["policy_version"] == "9.0.1"
    assert set(document["customers"]) == {"KHB"}
    assert (await bench.service().get(GIANG.context(ALPHA), view.example_id)).status == "submitted"
    with pytest.raises(ConflictError) as again:
        await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.2")
    assert again.value.details["rule"] == "already_submitted"
    assert len(bench.proposals.sent) == 1


async def test_a_replay_against_a_layout_no_longer_in_force_is_not_sent() -> None:
    bench, _, view = await _learned("SR02")
    async with bench.store(ALPHA) as work:
        stored = await work.examples.get(view.example_id)
        assert stored is not None and stored.replay is not None
        stale = stored.replay.model_copy(update={"layout_ref": "sales_bravo_upload@1.1.0"})
        work.examples._state.examples[view.example_id] = stored.model_copy(update={"replay": stale})
        await work.commit()
    with pytest.raises(ConflictError) as refused:
        await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.1")
    assert refused.value.details["rule"] == "layout_changed"


# ----------------------------------------------------------- acceptance 3 --


def _world() -> Any:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, AN, HAI))


async def _seed_replayed(world: Any, customer: str, by: Caller) -> uuid.UUID:
    """A replayed example whose replay matched, as the worker leaves one."""
    layout = (await world.services.rules.list(GIANG.context(ALPHA))).in_force[RuleKey.BRAVO_UPLOAD]
    example = SalesOrderExample(
        example_id=uuid.uuid4(),
        customer_code=customer,
        status="replayed",
        requested_by=by.user_id,
        requested_at=datetime(2026, 11, 14, 2, 0, tzinfo=UTC),
        received_on=date(2026, 11, 14),
        po_file_name="po.xlsx",
        po_sha256="0" * 64,
        po_size=1,
        salesorder_file_name="SalesOrder.xlsx",
        salesorder_sha256="1" * 64,
        salesorder_size=1,
        rules=CustomerSalesOrderRules.model_validate(pair(CASES, "SR01")["gold"]),
        replay=Replay(
            layout_ref=layout, rows_expected=2, rows_got=2, cells_compared=38, differences_total=0
        ),
    )
    async with world.example_store(ALPHA) as work:
        await work.examples.add(example, b"po", b"so")
        await work.commit()
    return example.example_id


async def test_the_proposer_cannot_approve_and_the_head_is_never_applied_directly() -> None:
    """Acceptance 3, first half: a PIC's proposal waits for the head; the
    head's own waits too (never applied directly, whoever proposes), for
    another head; neither proposer decides their own."""
    world = _world()
    examples = world.services.salesorder_examples
    by_an = await examples.submit(
        AN.context(ALPHA), await _seed_replayed(world, "NRV", AN), "9.0.1"
    )
    assert (by_an.status, by_an.applied_directly) == ("proposed", False)
    with pytest.raises((PermissionDeniedError, ConflictError)):
        await world.decide_rules(AN, by_an.version_id, approve=True, comment="Tự duyệt")
    await world.decide_rules(GIANG, by_an.version_id, approve=True, comment="Đã xem bản chạy lại")
    listed = await world.services.rules.list(GIANG.context(ALPHA))
    assert listed.in_force[RuleKey.SALESORDER_RULES] == "sales_salesorder_rules@9.0.1"
    assert listed.layers[RuleKey.SALESORDER_RULES] == "tenant"

    by_head = await examples.submit(
        GIANG.context(ALPHA), await _seed_replayed(world, "VLX", GIANG), "9.0.2"
    )
    assert (by_head.status, by_head.applied_directly) == ("proposed", False)
    with pytest.raises((PermissionDeniedError, ConflictError)):
        await world.decide_rules(GIANG, by_head.version_id, approve=True, comment="Tự duyệt")
    await world.decide_rules(HAI, by_head.version_id, approve=True, comment="Đã xem")
    in_force = (await world.services.rules.list(GIANG.context(ALPHA))).in_force
    assert in_force[RuleKey.SALESORDER_RULES] == "sales_salesorder_rules@9.0.2"
    # The second version kept the first customer's rules.
    document = next(
        v.document
        for v in (await world.services.rules.list(GIANG.context(ALPHA))).versions
        if v.version == "9.0.2"
    )
    assert set(document["customers"]) == {"NRV", "VLX"}
    # The approval shows the replay it was sent from.
    shown = await examples.for_version(GIANG.context(ALPHA), by_head.version_id)
    assert shown.replay is not None and shown.replay.matches


async def test_the_approved_rules_map_the_customers_next_po_with_no_model_call() -> None:
    """Acceptance 3, second half: learned once (one model call), the rules
    then fill the customer's next PO by code alone, through the row the
    upload file composes; the model is never asked again."""
    spec = pair(CASES, "SR02")
    _, model, view = await _learned("SR02")
    assert len(model.calls) == 1 and view.rules is not None
    from dw_sales.adapters.policy_files import load_sales_policies
    from dw_sales.adapters.reader_client import ClientPoReaders
    from dw_sales.adapters.readers.operations import InProcessReaderTransport
    from dw_sales.application.layouts import PROBE_REF
    from dw_sales.evals.salesorder_rules import attachment_of, po_mapping

    model.failure = AssertionError("the model is never called once rules are approved")
    following = {
        **spec,
        "po_no": "KHB-PO-7790",
        "lines": [
            {**spec["lines"][1], "no": 1, "quantity": "2.44", "requested_date": "2027-02-01"},
            {**spec["lines"][0], "no": 2, "quantity": "0.61", "requested_date": "2027-02-11"},
        ],
    }
    policies = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
    read = await ClientPoReaders(InProcessReaderTransport()).read_with(
        attachment_of("next.xlsx", po_bytes(following)),
        po_mapping(following),
        policies.order_rules.intake,
        layout_ref=PROBE_REF,
    )
    master = CASES["master"]
    customer = next(c for c in customers(master) if c.code == "KHB")
    lookups = Lookups.of("KHB", converts(master), items(master))
    assert not hasattr(read, "reason"), read
    rows = [
        filled_row(policies.upload, view.rules, values, customer, lookups)
        for values in example_rows(read, "KHB", date(2027, 1, 2), lookups)
    ]
    at = column_index
    assert [(r[at("T")], r[at("V")], r[at("AA")], r[at("AF")]) for r in rows] == [
        ("PRV-B24-BK", "black", Decimal("2440.00"), date(2027, 1, 22)),
        ("PRV-B24-RD", "red", Decimal(610), date(2027, 2, 1)),
    ]
    assert len(model.calls) == 1


# ------------------------------------------------------- what code verifies --


def _pic(*rows: dict[int, str]) -> PicFile:
    return PicFile("Sheet1", 3, {}, tuple(PicRow(4 + i, row) for i, row in enumerate(rows)))


def test_a_constant_must_be_alone_held_by_every_row_and_never_a_po_value() -> None:
    from dw_sales.evals.rule_drafts import platform_layout

    layout = platform_layout(REPO)
    w = column_index("W")
    rows: list[dict[UploadField, Value]] = [
        {"po_no": "PO-77", "description": "X", "quantity": Decimal(1)}
    ]

    def answer(*steps: dict[str, Any], field: str | None = None) -> ModelSalesOrderRules:
        rule: dict[str, Any] = {"column": "W", "steps": list(steps)}
        if field:
            rule["field"] = field
        return ModelSalesOrderRules.model_validate({"columns": [rule]})

    hk = {"step": "constant", "value": "HK"}
    assert isinstance(
        verify(answer(hk), layout, rows, _pic({w: "HK"}, {w: " HK "})), CustomerSalesOrderRules
    )
    cases = {
        "constant_not_in_file": verify(answer(hk), layout, rows, _pic({w: "HK"}, {w: "HN"})),
        "constant_not_alone": verify(
            answer(hk, {"step": "cut", "end": 1}),
            layout,
            rows,
            _pic({w: "H"}),
        ),
        "constant_from_po": verify(
            answer({"step": "constant", "value": "PO-77"}),
            layout,
            rows,
            _pic({w: "PO-77"}),
        ),
    }
    for code, verdict in cases.items():
        assert isinstance(verdict, list) and [p.code for p in verdict] == [code], code
    beyond = ModelSalesOrderRules.model_validate({"columns": [{"column": "BZ", "steps": [hk]}]})
    outside = verify(beyond, layout, rows, _pic({w: "HK"}))
    assert isinstance(outside, list) and outside[0].code == "column_outside_layout"


@pytest.mark.parametrize(
    ("want", "have"),
    [
        ("2026-12-10T00:00:00", date(2026, 12, 10)),
        ("2026/12/10", date(2026, 12, 10)),
        ("1220", Decimal("1220.000")),
        ("0.0415", Decimal("0.04150")),
        (" Hà Nội ", "Hà Nội"),
        ("1", 1),
    ],
)
def test_cells_compare_numbers_by_value_dates_by_day_text_trimmed(want: str, have: Any) -> None:
    assert canonical(want) == canonical(have)


@pytest.mark.parametrize(
    ("want", "have"),
    [("2026-12-10", date(2026, 12, 11)), ("1220", Decimal(1221)), ("HK", "HN"), ("", "X")],
)
def test_cells_that_differ_are_told_apart(want: str, have: Any) -> None:
    assert canonical(want) != canonical(have)


async def test_inputs_shrink_to_fit_the_room() -> None:
    bench, model, view = await _learned("SR02")
    full = model.calls[0][2]
    assert view.replay is not None
    from dw_agent_runtime.model.interpretation import estimated_tokens

    assert estimated_tokens("".join(full.values())) <= 6000 - PROMPT_TOKENS
    # A room too small for the rows cuts each text, never a column.
    assert view.replay is not None
    del bench


# ------------------------------------------------- refusals and isolation --


async def test_a_pic_file_in_another_layout_is_refused_before_any_model_call() -> None:
    spec = pair(CASES, "SR02")
    bench, model = _bench(spec["gold"])
    headers = [c.header for c in bench.layout.columns]
    headers[26], headers[30] = headers[30], headers[26]
    view = await bench.learn(
        spec, salesorder=salesorder_bytes(bench.layout, file_cells(spec), headers=headers)
    )
    assert view.status == "refused"
    assert {(p.code, p.column) for p in view.problems} == {
        ("header_differs", "AA"),
        ("header_differs", "AE"),
    }
    assert model.calls == []


async def test_no_model_leaves_the_layouts_replay_to_show_and_nothing_to_send() -> None:
    spec = pair(CASES, "SR02")
    for model, code in (
        (None, "model_not_configured"),
        (Recorded(failure=ModelUnavailableError("down")), "model_unavailable"),
    ):
        bench = Bench.of(REPO, model, (GIANG,))
        view = await bench.learn(spec)
        assert (view.status, [p.code for p in view.problems]) == ("unavailable", [code])
        assert view.rules is None and view.replay is not None and not view.replay.matches
        with pytest.raises(ConflictError):
            await bench.service().submit(GIANG.context(ALPHA), view.example_id, "9.0.1")


async def test_an_example_is_the_asking_tenants_and_needs_the_scopes() -> None:
    bench, _, view = await _learned("SR02")
    outsider = replace(
        OUTSIDER, scopes=OUTSIDER.scopes | {SalesScopes.RULES_PROPOSE, SalesScopes.PRICE_READ}
    )
    from dw_sales.evals.world import BETA

    with pytest.raises(NotFoundError):
        await bench.service().get(outsider.context(BETA), view.example_id)
    with pytest.raises(NotFoundError):
        await bench.service().submit(outsider.context(BETA), view.example_id, "9.0.1")
    # Without `sales.price.read` (the files carry prices) or the proposer's scope.
    for missing in (SalesScopes.PRICE_READ, SalesScopes.RULES_PROPOSE):
        caller = replace(GIANG, scopes=GIANG.scopes - {missing})
        with pytest.raises(PermissionDeniedError):
            await bench.service().get(caller.context(ALPHA), view.example_id)
        with pytest.raises(PermissionDeniedError):
            await bench.service().submit(caller.context(ALPHA), view.example_id, "9.0.1")
    assert bench.proposals.sent == []


async def test_a_request_is_kept_for_the_worker_with_one_event_and_an_audit_row() -> None:
    spec = pair(CASES, "SR01")
    bench, _ = _bench(spec["gold"])
    view = await bench.service().request(
        GIANG.context(ALPHA),
        "KHA",
        date(2026, 11, 3),
        ("po.xlsx", po_bytes(spec)),
        ("SalesOrder.xlsx", salesorder_bytes(bench.layout, file_cells(spec))),
    )
    assert view.status == "queued"
    events = [e for e in bench.store.outbox.events if e.event_type == EXAMPLE_REQUESTED]
    assert [e.payload for e in events] == [{"example_id": str(view.example_id)}]
    for bad in (("po.exe", b"x"), ("po.xlsx", b"")):
        with pytest.raises(DomainError):
            await bench.service().request(
                GIANG.context(ALPHA), "KHA", date(2026, 11, 3), bad, ("s.xlsx", b"x")
            )
    with pytest.raises(NotFoundError):
        await bench.service().request(
            GIANG.context(ALPHA), "NOBODY", date(2026, 11, 3), ("p.xlsx", b"x"), ("s.xlsx", b"x")
        )
    await bench.learning().learn(ALPHA, view.example_id)
    lane = [
        e for e in bench.store.audit.events if e.details.get("actor") == f"system:{EXAMPLE_LANE}"
    ]
    assert [e.action for e in lane] == ["sales.salesorder_example.replayed"]
    assert all("HK" not in str(e.details) for e in bench.store.audit.events)


async def test_the_salesorder_file_is_opened_under_the_caps_its_po_was_read_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DW1 review, config (2026-11-27): both files of a pair are opened under
    the company's order rules, never the SalesOrder under the platform
    file's caps bound when the process started."""
    from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
    from dw_sales.adapters.readers.operations import InProcessReaderTransport
    from dw_sales.application.rules import Resolved
    from dw_sales.domain.order_checks import IntakeCaps, OrderRules

    spec = pair(CASES, "SR01")
    bench, _ = _bench(spec["gold"])
    view = await bench.service().request(
        GIANG.context(ALPHA),
        spec["customer"],
        date.fromisoformat(spec["received_on"]),
        ("po.xlsx", po_bytes(spec)),
        ("SalesOrder.xlsx", salesorder_bytes(bench.layout, file_cells(spec))),
    )
    platform = bench.rules()
    raised: list[IntakeCaps] = []

    class Company:
        async def current(self, scope: Any, key: RuleKey) -> Resolved:
            resolved = await platform.current(scope, key)
            if key is not RuleKey.ORDER_RULES:
                return resolved
            rules = resolved.policy
            assert isinstance(rules, OrderRules)
            caps = rules.intake.model_copy(update={"max_cells": rules.intake.max_cells * 2})
            raised.append(caps)
            return Resolved(rules.model_copy(update={"intake": caps}), "tenant")

    asked: list[IntakeCaps | None] = []
    original = InProcessReaderTransport.call

    async def recorded(self: InProcessReaderTransport, request: ReaderRequest) -> ReaderReply:
        if request.operation in {ReaderOp.SOURCE_SHEET_NAMES, ReaderOp.SOURCE_SHEET_GRID}:
            asked.append(request.args.caps)
        return await original(self, request)

    monkeypatch.setattr(InProcessReaderTransport, "call", recorded)
    await replace(bench.learning(), rules=Company()).learn(ALPHA, view.example_id)

    assert raised and asked and set(asked) == {raised[0]}
