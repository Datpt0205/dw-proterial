"""A rule version drafted from a company's Bravo template ("Tạo từ tệp mẫu")."""

from __future__ import annotations

import asyncio
import json
import unicodedata
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, get_args

import pytest

from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import (
    DomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import SalesScopes
from dw_sales.application.artifact_content import BravoUploadLayout, UploadField
from dw_sales.application.malware import ScanVerdict
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.rule_drafts import (
    BRAVO_TEMPLATE_MAPPING,
    KEPT_FOR,
    PROMPT_TOKENS,
    RULE_DRAFT_REQUESTED,
    STALE_AFTER,
    RuleDrafting,
    Swept,
)
from dw_sales.application.rules import RuleKey
from dw_sales.application.source import SheetCell, SheetGrid
from dw_sales.application.template_reading import (
    ModelBravoMapping,
    Proposal,
    Refused,
    TemplateHeader,
    TemplateRow,
    header_row,
    mapping_inputs,
    offered,
    verify,
)
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import OUTSIDER as _OUTSIDER
from dw_sales.evals.graders import READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.rule_drafts import (
    ALPHA_OTHER,
    Bench,
    gold,
    hidden_texts,
    platform_layout,
    template_xlsx,
)
from dw_sales.evals.world import ALPHA, BETA, Caller

# An (and the others below) given the set `sales_rules_editor` (`sales.rules.propose`): since
# 2026-10-28 a PIC proposes only when the admin gives them it.
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
OUTSIDER = replace(_OUTSIDER, scopes=_OUTSIDER.scopes | {SalesScopes.RULES_PROPOSE})

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
_CASES = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_rule_drafts.json").read_text(encoding="utf-8")
)
GOLDEN: dict[str, Any] = _CASES["golden"][0]
INJECTION: dict[str, Any] = _CASES["injection"]
NO_QUANTITY: dict[str, Any] = _CASES["no_quantity"]
UNSEEN: dict[str, Any] = _CASES["unseen_text"]
BASE = platform_layout(REPO)


def _cell(ref: str, row: int, column: int, text: str, **flags: bool) -> SheetCell:
    return SheetCell(ref=ref, row=row, column=column, text=text, **{"text_unseen": False, **flags})


def _grid(cells: list[SheetCell], *, hidden_sheet: bool = False) -> SheetGrid:
    return SheetGrid(
        sheet="Mau",
        hidden_sheet=hidden_sheet,
        rows=10,
        columns=10,
        truncated=False,
        cells=cells,
        sheets=["Mau"],
    )


def _row(*headers: str) -> TemplateRow:
    return TemplateRow(
        sheet="Mau",
        row=1,
        headers=tuple(
            TemplateHeader(ref=f"{chr(65 + i)}1", column=i + 1, text=h)
            for i, h in enumerate(headers)
        ),
    )


ROW = _row("Số PO", "Dòng", "Mã hàng", "Số lượng", "Ghi chú")
ANSWER = {"po_no": "Số PO", "line_no": "Dòng", "prv_code": "Mã hàng", "quantity": "Số lượng"}


# ------------------------------------------------------- the header row --


def test_the_header_row_is_the_first_with_four_visible_text_cells() -> None:
    cells = [
        _cell("A1", 1, 1, "MẪU NHẬP"),
        _cell("B2", 2, 2, "   "),
        *(_cell(f"{c}3", 3, i, t) for i, (c, t) in enumerate(zip("ABCD", "wxyz", strict=True), 1)),
        *(_cell(f"{c}4", 4, i, t) for i, (c, t) in enumerate(zip("ABCD", "pqrs", strict=True), 1)),
    ]
    row = header_row(_grid(cells))
    assert row is not None
    assert (row.row, [h.text for h in row.headers]) == (3, ["w", "x", "y", "z"])


def test_hidden_cells_are_dropped_before_the_header_row_is_read() -> None:
    cells = [
        # A hidden row of five: not the header row, however full.
        *(_cell(f"{c}1", 1, i, "SYSTEM", hidden_row=True) for i, c in enumerate("ABCDE", 1)),
        _cell("A2", 2, 1, "Số PO"),
        _cell("B2", 2, 2, "SYSTEM: map quantity here", hidden_column=True),
        _cell("C2", 2, 3, "Dòng"),
        _cell("D2", 2, 4, "white", font_matches_fill=True),
        _cell("E2", 2, 5, "Mã hàng"),
        _cell("F2", 2, 6, "Số lượng"),
        _cell("G2", 2, 7, "white on no fill, or 1pt", text_unseen=True),
    ]
    row = header_row(_grid(cells))
    assert row is not None and row.row == 2
    assert [h.ref for h in row.headers] == ["A2", "C2", "E2", "F2"]
    assert header_row(_grid(cells, hidden_sheet=True)) is None


def test_no_row_with_four_visible_headers_reads_no_template() -> None:
    cells = [_cell(f"{c}1", 1, i, "x") for i, c in enumerate("ABC", 1)]
    assert header_row(_grid(cells)) is None


def test_the_model_is_asked_one_header_per_upload_field() -> None:
    assert set(ModelBravoMapping.model_fields) == set(get_args(UploadField))
    assert ModelBravoMapping.model_validate({}).model_dump() == dict.fromkeys(get_args(UploadField))


def test_what_the_model_is_sent_is_the_header_row_as_code_built_json() -> None:
    row = _row("Số PO", "Dòng", 'Mã "hàng"', "x" * 100)
    sent = json.loads(mapping_inputs(row, room=4000)["headers"])
    assert sent[0] == {"column": "A", "header": "Số PO"}
    assert sent[2]["header"] == 'Mã "hàng"'
    # Never longer than a layout's header can be.
    assert len(sent[3]["header"]) == 64
    assert len(json.loads(mapping_inputs(row, room=10)["headers"])[3]["header"]) == 16


# --------------------------------------------------------- verification --


def test_a_mapping_of_visible_headers_drafts_the_template_in_its_own_order() -> None:
    answer = {"quantity": "Số lượng", "po_no": "Số PO", "prv_code": "Mã hàng", "line_no": "Dòng"}
    drafted = verify(answer, ROW, BASE)
    assert isinstance(drafted, Proposal)
    layout = BravoUploadLayout.model_validate(drafted.document)
    assert [(c.field, c.header) for c in layout.columns] == [
        ("po_no", "Số PO"),
        ("line_no", "Dòng"),
        ("prv_code", "Mã hàng"),
        ("quantity", "Số lượng"),
    ]
    assert (layout.sheet_name, layout.mock) == ("Mau", False)
    assert drafted.evidence["columns.3.header"] == "Mau!D1"
    assert drafted.evidence["sheet_name"] == "Mau!A1:E1"
    assert set(drafted.machine_read) == set(drafted.evidence)
    assert [(p.code, p.ref, p.header) for p in drafted.problems] == [
        ("column_unmapped", "E1", "Ghi chú")
    ]


def test_a_header_the_template_does_not_hold_verbatim_is_refused() -> None:
    for invented in ("so luong", "Số Lượng", "Số lượng đặt"):
        refused = verify({**ANSWER, "quantity": invented}, ROW, BASE)
        assert isinstance(refused, Refused)
        assert [(p.code, p.field) for p in refused.problems] == [
            ("header_not_in_template", "quantity")
        ]


def test_one_column_for_two_fields_is_refused() -> None:
    refused = verify({**ANSWER, "unit_price": "Số lượng"}, ROW, BASE)
    assert isinstance(refused, Refused)
    assert {(p.code, p.field, p.ref) for p in refused.problems} == {
        ("header_twice", "quantity", "D1"),
        ("header_twice", "unit_price", "D1"),
    }


def test_a_header_printed_twice_cannot_say_which_column() -> None:
    row = _row("Số PO", "Dòng", "Mã hàng", "Số lượng", "Số lượng")
    refused = verify(ANSWER, row, BASE)
    assert isinstance(refused, Refused)
    assert [(p.code, p.field) for p in refused.problems] == [("header_ambiguous", "quantity")]


def test_a_required_field_left_out_is_refused_by_name() -> None:
    refused = verify({"po_no": "Số PO", "line_no": "Dòng", "description": ""}, ROW, BASE)
    assert isinstance(refused, Refused)
    assert [(p.code, p.field) for p in refused.problems] == [
        ("required_missing", "prv_code"),
        ("required_missing", "quantity"),
    ]


def test_a_header_is_compared_and_written_nfc_without_surrounding_spaces() -> None:
    decomposed = unicodedata.normalize("NFD", "Số lượng")
    row = _row("Số PO", "Dòng", "Mã hàng", f"  {decomposed} ")
    for asked in ("Số lượng", f"{decomposed}  ", " Số lượng"):
        drafted = verify({**ANSWER, "quantity": asked}, row, BASE)
        assert isinstance(drafted, Proposal), asked
        assert drafted.document["columns"][3] == {"field": "quantity", "header": "Số lượng"}
        assert drafted.evidence["columns.3.header"] == "Mau!D1"


def test_a_header_longer_than_a_layout_holds_is_refused_by_name_and_cell() -> None:
    long = "Số lượng đặt hàng theo đơn vị tính của khách hàng (bao gồm hàng tặng kèm)"
    assert len(long) > 64
    row = _row("Số PO", "Dòng", "Mã hàng", long)
    # The model saw the header cut to what a layout holds (`mapping_inputs`),
    # and may answer that or the whole text: either way, the cell is named.
    shown = json.loads(mapping_inputs(row, room=4000)["headers"])[3]["header"]
    for asked in (long, shown):
        refused = verify({**ANSWER, "quantity": asked}, row, BASE)
        assert isinstance(refused, Refused)
        assert [(p.code, p.field, p.ref) for p in refused.problems] == [
            ("header_too_long", "quantity", "D1")
        ]


def test_a_mapping_that_is_no_valid_layout_is_refused_with_where() -> None:
    row = TemplateRow(sheet="Mẫu: nhập", row=1, headers=ROW.headers)
    refused = verify(ANSWER, row, BASE)
    assert isinstance(refused, Refused)
    assert [(p.code, p.where) for p in refused.problems] == [("layout_invalid", "sheet_name")]


def test_without_a_mapping_only_the_sheet_read_is_offered() -> None:
    fallback = offered(ROW, BASE)
    assert fallback.document["columns"] == BASE.model_dump(mode="json")["columns"]
    assert (fallback.document["sheet_name"], fallback.machine_read) == ("Mau", ("sheet_name",))
    bad = TemplateRow(sheet="Mẫu: nhập", row=1, headers=ROW.headers)
    kept = offered(bad, BASE)
    assert kept.document["sheet_name"] == BASE.sheet_name
    assert [p.code for p in kept.problems] == ["sheet_name_invalid"]


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        BRAVO_TEMPLATE_MAPPING.prompt_id,
        BRAVO_TEMPLATE_MAPPING.version,
        {"headers": "[]"},
        tenant_id=uuid.uuid4(),
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
    # Every field the model is asked is described to it.
    for name in get_args(UploadField):
        assert f"- {name}:" in rendered.system


# --------------------------------------------------- request and draft --


def test_a_request_keeps_the_file_and_asks_the_worker() -> None:
    bench = Bench.of(REPO, None, (AN,))
    data = template_xlsx(GOLDEN)
    view = asyncio.run(
        bench.service().request(AN.context(), RuleKey.BRAVO_UPLOAD, "mau.xlsx", data)
    )
    assert view.status == "queued" and view.document is None
    state = bench.store.state(ALPHA)
    assert state.files[view.draft_id] == data
    assert [e.event_type for e in bench.store.outbox.events] == [RULE_DRAFT_REQUESTED]
    assert bench.store.outbox.events[0].payload == {"draft_id": str(view.draft_id)}
    assert [e.action for e in bench.store.audit.events] == ["sales.rule_draft.requested"]


@pytest.mark.parametrize(
    ("key", "name", "size", "rule"),
    [
        (RuleKey.EMAILS, "mau.xlsx", 1, "key_not_draftable"),
        (RuleKey.BRAVO_UPLOAD, "mau.csv", 1, "file_type"),
        (RuleKey.BRAVO_UPLOAD, "mau.pdf", 1, "file_type"),
        (RuleKey.BRAVO_UPLOAD, "mau.xlsx", 0, "file_empty"),
        (RuleKey.BRAVO_UPLOAD, "mau.xlsx", 2 * 1024 * 1024 + 1, "file_size"),
        (RuleKey.BRAVO_UPLOAD, "a/b.xlsx", 1, "file_name"),
    ],
)
def test_a_request_is_refused_with_its_reason(
    key: RuleKey, name: str, size: int, rule: str
) -> None:
    bench = Bench.of(REPO, None, (AN,))
    with pytest.raises(DomainError) as refused:
        asyncio.run(bench.service().request(AN.context(), key, name, b"x" * size))
    assert refused.value.details["rule"] == rule
    assert bench.store.state(ALPHA).drafts == {}


def test_only_a_proposer_requests_or_reads_a_draft() -> None:
    bench = Bench.of(REPO, None, (AN, READER))
    with pytest.raises(PermissionDeniedError):
        asyncio.run(bench.service().request(READER.context(), RuleKey.BRAVO_UPLOAD, "m.xlsx", b"x"))
    with pytest.raises(PermissionDeniedError):
        asyncio.run(bench.service().get(READER.context(), uuid.uuid4()))


def test_the_right_mapping_is_drafted_ready_and_the_file_dropped() -> None:
    model = Recorded(raw=gold(GOLDEN))
    bench = Bench.of(REPO, model, (AN,))
    view = asyncio.run(bench.draft(GOLDEN))
    assert view.status == "ready", view.problems
    layout = BravoUploadLayout.model_validate(view.document)
    assert [c.header for c in layout.columns] == [h for h, f in GOLDEN["columns"] if f]
    assert layout.sheet_name == GOLDEN["sheet"]
    assert view.template is not None and view.template.sheet == GOLDEN["sheet"]
    assert "columns.0.header" in view.machine_read
    assert view.evidence["columns.0.header"] == f"{GOLDEN['sheet']}!A3"
    assert [p.code for p in view.problems] == ["column_unmapped"]
    assert (view.prompt_ref, view.model_profile) == (str(BRAVO_TEMPLATE_MAPPING), "onprem")
    assert bench.store.state(ALPHA).files == {}
    audit = bench.store.audit.events[-1]
    assert (audit.action, audit.details["actor"]) == (
        "sales.rule_draft.ready",
        "system:sales_rule_drafts",
    )
    # A second delivery of the same event finds it settled.
    assert asyncio.run(bench.drafting().draft(ALPHA, view.draft_id)) == "draft not queued"


def test_nothing_hidden_in_the_template_reaches_the_model() -> None:
    model = Recorded(raw=gold(INJECTION))
    view = asyncio.run(Bench.of(REPO, model, (AN,)).draft(INJECTION))
    sent = "".join("".join(inputs.values()) for _, _, inputs in model.calls)
    assert hidden_texts(INJECTION)
    for text in hidden_texts(INJECTION):
        assert text not in sent
    assert "Số lượng" in sent
    assert view.status == "ready"


def test_white_text_on_no_fill_and_1pt_text_never_reach_the_model() -> None:
    model = Recorded(raw=gold(UNSEEN))
    view = asyncio.run(Bench.of(REPO, model, (AN,)).draft(UNSEEN))
    (sent,) = ("".join(inputs.values()) for _, _, inputs in model.calls)
    assert [UNSEEN["white_unfilled"], UNSEEN["tiny_text"]] == hidden_texts(UNSEEN)
    for text in hidden_texts(UNSEEN):
        assert text not in sent
    # Headers printed white on a dark fill are seen, and sent.
    for header, _ in UNSEEN["columns"]:
        assert header in sent
    assert view.template is not None
    assert [h.text for h in view.template.headers] == [h for h, _ in UNSEEN["columns"]]
    assert view.status == "ready"


@pytest.mark.parametrize("key", ["white_unfilled", "tiny_text"])
def test_a_header_only_an_unseen_cell_holds_is_refused(key: str) -> None:
    answer = {**gold(UNSEEN), "quantity": UNSEEN[key]}
    view = asyncio.run(Bench.of(REPO, Recorded(raw=answer), (AN,)).draft(UNSEEN))
    assert view.status == "refused"
    assert ("header_not_in_template", "quantity") in [(p.code, p.field) for p in view.problems]


def test_a_header_only_a_hidden_cell_holds_is_refused() -> None:
    answer = {**gold(INJECTION), "quantity": INJECTION["hidden_columns"][0]["header"]}
    view = asyncio.run(Bench.of(REPO, Recorded(raw=answer), (AN,)).draft(INJECTION))
    assert view.status == "refused"
    assert ("header_not_in_template", "quantity") in [(p.code, p.field) for p in view.problems]
    # Refused, it still starts from something: the version in force, the sheet read.
    assert view.machine_read == ["sheet_name"]
    assert (
        view.document is not None
        and view.document["columns"] == BASE.model_dump(mode="json")["columns"]
    )


def test_a_template_with_no_quantity_is_refused_by_name() -> None:
    view = asyncio.run(Bench.of(REPO, Recorded(raw=gold(NO_QUANTITY)), (AN,)).draft(NO_QUANTITY))
    assert view.status == "refused"
    assert [(p.code, p.field) for p in view.problems] == [("required_missing", "quantity")]


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (None, "model_not_configured"),
        (Recorded(failure=ModelUnavailableError("down")), "model_unavailable"),
        (Recorded(raw={"po_no": 7}), "model_unavailable"),
    ],
)
def test_without_a_usable_answer_the_draft_offers_the_headers(model: Any, why: str) -> None:
    view = asyncio.run(Bench.of(REPO, model, (AN,)).draft(GOLDEN))
    assert view.status == "unavailable"
    assert [p.code for p in view.problems] == [why]
    assert view.document is not None and view.document["sheet_name"] == GOLDEN["sheet"]
    assert view.template is not None
    assert [h.text for h in view.template.headers] == [h for h, _ in GOLDEN["columns"]]


def test_a_spent_plan_day_degrades_and_does_not_retry() -> None:
    from dw_kernel.errors import QuotaExceededError

    model = Recorded(failure=QuotaExceededError("hết lượt"))
    view = asyncio.run(Bench.of(REPO, model, (AN,)).draft(GOLDEN))
    assert (view.status, [p.code for p in view.problems]) == ("unavailable", ["model_quota"])


def test_the_model_call_is_the_askers_on_dw1s_worker() -> None:
    model = Recorded(raw=gold(GOLDEN))
    asyncio.run(Bench.of(REPO, model, (AN,)).draft(GOLDEN))
    _, run, _ = model.calls[0]
    assert (run.tenant_id, run.actor_id, run.worker_id) == (
        ALPHA.tenant_id.value,
        AN.user_id,
        "sales-dw1",
    )
    assert run.plan_id == "professional"
    assert run.scopes == frozenset({"sales.rules.propose"})


def test_an_asker_who_lost_the_scope_gets_nothing_drafted() -> None:
    model = Recorded(raw=gold(GOLDEN))
    bench = Bench.of(REPO, model, (AN,))
    requested = asyncio.run(
        bench.service().request(AN.context(), RuleKey.BRAVO_UPLOAD, "m.xlsx", template_xlsx(GOLDEN))
    )
    demoted = Caller(AN.user_id, AN.name, AN.email, frozenset({"sales.case.read"}))
    drafting = Bench.of(REPO, model, (demoted,))
    drafting.store = bench.store
    asyncio.run(drafting.drafting().draft(ALPHA, requested.draft_id))
    view = asyncio.run(bench.service().get(AN.context(), requested.draft_id))
    assert (view.status, view.document, model.calls) == ("failed", None, [])
    assert view.error == "người tải tệp không còn quyền đề xuất quy tắc"


def test_an_infected_file_fails_and_a_silent_scanner_retries() -> None:
    from dataclasses import replace

    from dw_sales.testing.scanners import ScriptedScanner

    data = template_xlsx(GOLDEN)
    for verdict, outcome in (
        (ScanVerdict.infected("Eicar-Test"), "failed"),
        (ScanVerdict.unavailable("down"), None),
    ):
        bench = Bench.of(REPO, Recorded(raw=gold(GOLDEN)), (AN,))
        requested = asyncio.run(
            bench.service().request(AN.context(), RuleKey.BRAVO_UPLOAD, "m.xlsx", data)
        )
        drafting: RuleDrafting = replace(bench.drafting(), scanner=ScriptedScanner({data: verdict}))
        if outcome is None:
            with pytest.raises(InfrastructureError):
                asyncio.run(drafting.draft(ALPHA, requested.draft_id))
            assert bench.store.state(ALPHA).drafts[requested.draft_id].status == "queued"
        else:
            asyncio.run(drafting.draft(ALPHA, requested.draft_id))
            view = asyncio.run(bench.service().get(AN.context(), requested.draft_id))
            assert (view.status, view.error) == ("failed", "tệp bị trình quét mã độc chặn")


def test_a_file_that_is_no_workbook_fails_with_its_reason() -> None:
    bench = Bench.of(REPO, Recorded(raw=gold(GOLDEN)), (AN,))
    requested = asyncio.run(
        bench.service().request(AN.context(), RuleKey.BRAVO_UPLOAD, "m.xlsx", b"%PDF-1.4 x")
    )
    asyncio.run(bench.drafting().draft(ALPHA, requested.draft_id))
    view = asyncio.run(bench.service().get(AN.context(), requested.draft_id))
    assert (view.status, view.error) == ("failed", "tệp không phải bảng tính Excel")


class _OlderReader:
    """The reader image of before `SheetCell.text_unseen`: the same answers,
    without that field (the e2e run of 2026-10-21 met one)."""

    async def call(self, request: ReaderRequest) -> ReaderReply:
        reply = await InProcessReaderTransport().call(request)
        if request.operation is ReaderOp.SOURCE_SHEET_GRID and isinstance(reply.result, dict):
            cells = reply.result["cells"]
            assert isinstance(cells, list)
            older = [
                {k: v for k, v in cell.items() if k != "text_unseen"}
                for cell in cells
                if isinstance(cell, dict)
            ]
            return reply.model_copy(update={"result": {**reply.result, "cells": older}})
        return reply


def test_a_reader_of_another_version_fails_the_draft_with_why_and_is_not_retried() -> None:
    """Sales defect B: the reply's ValidationError escaped, the outbox
    delivered the event again, and the editor said "Đang đọc tệp"."""
    from dataclasses import replace

    from dw_sales.adapters.reader_client import ClientSourceView

    bench = Bench.of(REPO, Recorded(raw=gold(GOLDEN)), (AN,))
    requested = asyncio.run(
        bench.service().request(AN.context(), RuleKey.BRAVO_UPLOAD, "m.xlsx", template_xlsx(GOLDEN))
    )
    sheets = ClientSourceView(_OlderReader(), bench.drafting().sheets.caps)  # type: ignore[attr-defined]
    drafting = replace(bench.drafting(), sheets=sheets)

    assert asyncio.run(drafting.draft(ALPHA, requested.draft_id)) == "draft failed"

    view = asyncio.run(bench.service().get(AN.context(), requested.draft_id))
    assert view.status == "failed"
    assert view.error is not None
    assert view.error.startswith("không mở được tệp mẫu: trình đọc tệp trả lời không khớp")
    assert view.document is None


def test_another_tenant_or_workspace_does_not_find_a_draft() -> None:
    bench = Bench.of(REPO, Recorded(raw=gold(GOLDEN)), (AN, OUTSIDER))
    view = asyncio.run(bench.draft(GOLDEN))
    for caller, scope in ((OUTSIDER, BETA), (AN, ALPHA_OTHER)):
        with pytest.raises(NotFoundError):
            asyncio.run(bench.service().get(caller.context(scope), view.draft_id))


def test_a_request_drops_the_workspaces_old_drafts() -> None:
    bench = Bench.of(REPO, None, (AN,))
    view = asyncio.run(bench.draft(GOLDEN))
    state = bench.store.state(ALPHA)
    old = state.drafts[view.draft_id]
    state.drafts[view.draft_id] = old.model_copy(
        update={"requested_at": old.requested_at - KEPT_FOR - timedelta(minutes=1)}
    )
    newer = asyncio.run(bench.draft(GOLDEN))
    assert set(bench.store.state(ALPHA).drafts) == {newer.draft_id}


# ------------------------------------------------------------- the sweep --


def _request(bench: Bench, scope: Any = ALPHA, *, aged: timedelta = timedelta(0)) -> uuid.UUID:
    """A draft requested ``aged`` ago and never read, as an event lost on
    the way leaves it."""
    view = asyncio.run(
        bench.service().request(
            AN.context(scope), RuleKey.BRAVO_UPLOAD, "m.xlsx", template_xlsx(GOLDEN)
        )
    )
    state = bench.store.state(scope)
    stored = state.drafts[view.draft_id]
    state.drafts[view.draft_id] = stored.model_copy(
        update={"requested_at": stored.requested_at - aged}
    )
    return view.draft_id


def test_the_sweep_fails_a_draft_its_event_lost_and_drops_its_file() -> None:
    bench = Bench.of(REPO, None, (AN,))
    lost = _request(bench, aged=STALE_AFTER + timedelta(minutes=1))
    reading = _request(bench, aged=STALE_AFTER - timedelta(minutes=1))
    sweep = bench.sweep()
    assert asyncio.run(sweep.due()) == [ALPHA]
    assert asyncio.run(sweep.sweep(ALPHA)) == Swept(expired=1, pruned=0)
    state = bench.store.state(ALPHA)
    assert set(state.files) == {reading}
    assert state.drafts[reading].status == "queued"
    view = asyncio.run(bench.service().get(AN.context(), lost))
    assert (view.status, view.error) == (
        "failed",
        "DW1 không đọc xong tệp trong 1 giờ: hãy tải lại tệp mẫu",
    )
    audit = bench.store.audit.events[-1]
    assert (audit.action, audit.resource_id, audit.details["actor"]) == (
        "sales.rule_draft.failed",
        str(lost),
        "system:sales_rule_drafts",
    )
    assert audit.details["reason"] == "stale"
    # Nothing is due any more until the second one is stale too.
    assert asyncio.run(sweep.due()) == []


def test_the_sweep_drops_old_drafts_with_no_request_to_come_for_them() -> None:
    bench = Bench.of(REPO, Recorded(raw=gold(GOLDEN)), (AN,))
    old = asyncio.run(bench.draft(GOLDEN)).draft_id
    kept = asyncio.run(bench.draft(GOLDEN)).draft_id
    # Aged after the last request: nobody asks again in this workspace.
    state = bench.store.state(ALPHA)
    stored = state.drafts[old]
    state.drafts[old] = stored.model_copy(
        update={"requested_at": stored.requested_at - KEPT_FOR - timedelta(minutes=1)}
    )
    assert asyncio.run(bench.sweep().due()) == [ALPHA]
    assert asyncio.run(bench.sweep().sweep(ALPHA)) == Swept(expired=0, pruned=1)
    assert set(bench.store.state(ALPHA).drafts) == {kept}


def test_the_sweep_visits_only_workspaces_with_something_due() -> None:
    bench = Bench.of(REPO, None, (AN,))
    _request(bench, ALPHA_OTHER)
    lost = _request(bench, ALPHA, aged=STALE_AFTER + timedelta(minutes=1))
    assert asyncio.run(bench.sweep().due()) == [ALPHA]
    asyncio.run(bench.sweep().sweep(ALPHA_OTHER))
    assert bench.store.state(ALPHA).drafts[lost].status == "queued"
    assert [d.status for d in bench.store.state(ALPHA_OTHER).drafts.values()] == ["queued"]
