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

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import (
    DomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_platform.application.malware import ScanVerdict
from dw_sales.adapters.reader_wire import ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import SalesScopes
from dw_sales.application.artifact_content import BravoUploadLayout, CustomerAttribute, UploadField
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
    repeated_values,
    verify,
)
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import OUTSIDER as _OUTSIDER
from dw_sales.evals.graders import READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.rule_drafts import (
    ALPHA_OTHER,
    Bench,
    answer_with,
    gold,
    hidden_texts,
    letter_of,
    platform_layout,
    template_xlsx,
    unseen_letters,
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


def _answer(**sources: str | dict[str, str]) -> ModelBravoMapping:
    """The model's answer: each column letter with its source, a field by
    its bare name."""
    return ModelBravoMapping.model_validate(
        {
            "columns": [
                {"column": letter, **({"field": s} if isinstance(s, str) else s)}
                for letter, s in sources.items()
            ]
        }
    )


ANSWER = {"A": "po_no", "B": "line_no", "C": "prv_code", "D": "quantity"}


def _drafted(document: dict[str, Any]) -> list[tuple[str, str | None, str | None, str | None]]:
    layout = BravoUploadLayout.model_validate(document)
    return [(c.header, c.field, c.customer, c.constant) for c in layout.columns]


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
    # What is above it is kept, row by row, for the layout's banner.
    assert [[h.ref for h in above] for above in row.above] == [["A1"], []]


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
    # The hidden row above is kept as an empty one: nothing of it is read.
    assert row.above == ((),)
    assert header_row(_grid(cells, hidden_sheet=True)) is None


def test_no_row_with_four_visible_headers_reads_no_template() -> None:
    cells = [_cell(f"{c}1", 1, i, "x") for i, c in enumerate("ABC", 1)]
    assert header_row(_grid(cells)) is None


def test_a_value_every_filled_row_repeats_is_read_and_nothing_else() -> None:
    cells = [
        *(_cell(f"{c}1", 1, i, t) for i, (c, t) in enumerate(zip("ABCD", "wxyz", strict=True), 1)),
        _cell("A2", 2, 1, "Mass"),
        _cell("A3", 3, 1, " Mass "),
        _cell("B2", 2, 2, "PO-1"),
        _cell("B3", 3, 2, "PO-2"),
        _cell("C2", 2, 3, "X"),
        _cell("C3", 3, 3, "SYSTEM", hidden_row=True),
        _cell("D2", 2, 4, "white", font_matches_fill=True),
        _cell("D3", 3, 4, "white", font_matches_fill=True),
    ]
    grid = _grid(cells)
    row = header_row(grid)
    assert row is not None
    repeated = repeated_values(grid, row)
    # A: one value on every row; B: two; C: the hidden row is not a row
    # anyone sees; D: nothing seen at all.
    assert {column: cell.ref for column, cell in repeated.items()} == {1: "A2", 3: "C2"}


def test_the_model_answers_each_column_by_its_letter_from_the_closed_sets() -> None:
    with pytest.raises(ValueError, match="field"):
        _answer(A={"field": "po_number"})
    with pytest.raises(ValueError, match="customer"):
        _answer(A={"customer": "credit_limit"})
    with pytest.raises(ValueError, match="column"):
        _answer(**{"Số PO": "po_no"})


def test_what_the_model_is_sent_is_the_header_row_as_code_built_json() -> None:
    row = _row("Số PO", "Dòng", 'Mã "hàng"', "x" * 100)
    repeated = {2: TemplateHeader(ref="B2", column=2, text="y" * 100)}
    sent = json.loads(mapping_inputs(row, repeated, room=4000)["headers"])
    assert sent[0] == {"column": "A", "header": "Số PO"}
    assert sent[1] == {"column": "B", "header": "Dòng", "every_row": "y" * 64}
    assert sent[2]["header"] == 'Mã "hàng"'
    assert len(sent[3]["header"]) == 64
    assert len(json.loads(mapping_inputs(row, {}, room=10)["headers"])[3]["header"]) == 16


# --------------------------------------------------------- verification --


def test_a_mapping_drafts_every_template_column_at_its_place() -> None:
    answer = _answer(D="quantity", A="po_no", C="prv_code", B="line_no")
    drafted = verify(answer, ROW, BASE, {})
    assert isinstance(drafted, Proposal)
    assert _drafted(drafted.document) == [
        ("Số PO", "po_no", None, None),
        ("Dòng", "line_no", None, None),
        ("Mã hàng", "prv_code", None, None),
        ("Số lượng", "quantity", None, None),
        # A column no source names is still the template's, left blank.
        ("Ghi chú", None, None, None),
    ]
    layout = BravoUploadLayout.model_validate(drafted.document)
    assert (layout.sheet_name, layout.mock, layout.schema_version) == ("Mau", False, "2.0")
    assert drafted.evidence["columns.3.header"] == "Mau!D1"
    assert drafted.evidence["columns.3.field"] == "Mau!D1"
    assert drafted.evidence["sheet_name"] == "Mau!A1:E1"
    assert set(drafted.machine_read) == set(drafted.evidence)
    assert [(p.code, p.ref, p.header) for p in drafted.problems] == [
        ("column_unmapped", "E1", "Ghi chú")
    ]
    # The version in force's format for the same field is kept.
    assert drafted.document["columns"][3]["number_format"] == "#,##0"


def test_a_header_printed_twice_is_two_columns_each_by_its_letter() -> None:
    """Bravo's template prints "Delivery term" at N and again at AK: a
    column is its letter, so each takes its own source, or none."""
    row = _row("Số PO", "Dòng", "Mã hàng", "Số lượng", "Delivery term", "Delivery term")
    answer = _answer(**ANSWER, E={"customer": "delivery_term"})
    drafted = verify(answer, row, BASE, {})
    assert isinstance(drafted, Proposal)
    assert _drafted(drafted.document)[4:] == [
        ("Delivery term", None, "delivery_term", None),
        ("Delivery term", None, None, None),
    ]
    assert [p.ref for p in drafted.problems] == ["F1"]


def test_a_column_the_header_row_does_not_have_is_refused() -> None:
    for letter in ("F", "Z", "AA"):
        refused = verify(_answer(**{**ANSWER, letter: "unit_price"}), ROW, BASE, {})
        assert isinstance(refused, Refused)
        assert [(p.code, p.field, p.ref) for p in refused.problems] == [
            ("header_not_in_template", "unit_price", letter)
        ]


def test_a_column_answered_twice_or_with_two_sources_is_refused() -> None:
    twice = ModelBravoMapping.model_validate(
        {
            "columns": [
                *_answer(**ANSWER).model_dump()["columns"],
                {"column": "D", "field": "unit_price"},
            ]
        }
    )
    refused = verify(twice, ROW, BASE, {})
    assert isinstance(refused, Refused)
    assert {(p.code, p.field, p.ref) for p in refused.problems} == {
        ("header_twice", "quantity", "D1"),
        ("header_twice", "unit_price", "D1"),
        ("required_missing", "quantity", None),
    }
    both = _answer(**ANSWER, E={"field": "uom", "customer": "destination"})
    refused = verify(both, ROW, BASE, {})
    assert isinstance(refused, Refused)
    assert [(p.code, p.ref) for p in refused.problems] == [("source_invalid", "E1")]


def test_one_field_on_two_columns_is_refused() -> None:
    refused = verify(_answer(**ANSWER, E="quantity"), ROW, BASE, {})
    assert isinstance(refused, Refused)
    assert [(p.code, p.field) for p in refused.problems] == [("field_twice", "quantity")]


def test_a_required_field_left_out_is_refused_by_name() -> None:
    refused = verify(_answer(A="po_no", B="line_no"), ROW, BASE, {})
    assert isinstance(refused, Refused)
    assert [(p.code, p.field) for p in refused.problems] == [
        ("required_missing", "quantity"),
        ("required_missing", "customer_item_code"),
    ]


def test_the_item_is_named_by_either_of_its_codes() -> None:
    drafted = verify(_answer(**{**ANSWER, "C": "customer_item_code"}), ROW, BASE, {})
    assert isinstance(drafted, Proposal)


def test_a_fixed_value_is_only_the_value_every_row_of_its_column_holds() -> None:
    repeated = {5: TemplateHeader(ref="E7", column=5, text="XA")}
    drafted = verify(_answer(**ANSWER, E={"constant": " XA "}), ROW, BASE, repeated)
    assert isinstance(drafted, Proposal)
    assert _drafted(drafted.document)[4] == ("Ghi chú", None, None, "XA")
    # Cited where it was read: the row below the header.
    assert drafted.evidence["columns.4.constant"] == "Mau!E7"
    for constant, at in (("XB", repeated), ("XA", {})):
        refused = verify(_answer(**ANSWER, E={"constant": constant}), ROW, BASE, at)
        assert isinstance(refused, Refused)
        assert [(p.code, p.ref) for p in refused.problems] == [("constant_not_in_template", "E1")]


def test_a_header_is_written_nfc_without_surrounding_spaces() -> None:
    decomposed = unicodedata.normalize("NFD", "Số lượng")
    row = _row("Số PO", "Dòng", "Mã hàng", f"  {decomposed} ")
    drafted = verify(_answer(**ANSWER), row, BASE, {})
    assert isinstance(drafted, Proposal)
    assert drafted.document["columns"][3]["header"] == "Số lượng"


def test_a_header_longer_than_a_layout_holds_is_refused_by_its_cell() -> None:
    long = "Số lượng " * 30
    assert len(long.strip()) > 200
    row = _row("Số PO", "Dòng", "Mã hàng", long)
    refused = verify(_answer(**ANSWER), row, BASE, {})
    assert isinstance(refused, Refused)
    assert [(p.code, p.ref) for p in refused.problems] == [("header_too_long", "D1")]


def test_the_rows_above_the_header_row_are_drafted_as_the_banner() -> None:
    above = (
        (TemplateHeader(ref="A1", column=1, text="File import"),),
        (),
        (
            TemplateHeader(ref="A3", column=1, text="ĐẦU"),
            TemplateHeader(ref="C3", column=3, text="CHI TIẾT"),
        ),
    )
    row = ROW.model_copy(update={"row": 4, "above": above})
    drafted = verify(_answer(**ANSWER), row, BASE, {})
    assert isinstance(drafted, Proposal)
    layout = BravoUploadLayout.model_validate(drafted.document)
    assert [[(c.text, c.first, c.last) for c in cells] for cells in layout.banner] == [
        [("File import", 1, 5)],
        [],
        [("ĐẦU", 1, 2), ("CHI TIẾT", 3, 5)],
    ]
    assert drafted.evidence["banner.2.1.text"] == "Mau!C3"


def test_a_mapping_that_is_no_valid_layout_is_refused_with_where() -> None:
    row = TemplateRow(sheet="Mẫu: nhập", row=1, headers=ROW.headers)
    refused = verify(_answer(**ANSWER), row, BASE, {})
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
    # Every field and customer value the model may answer is described to it.
    for name in (*get_args(UploadField), *get_args(CustomerAttribute)):
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
    assert [c.header for c in layout.columns] == [h for h, _ in GOLDEN["columns"]]
    assert [c.field for c in layout.columns] == [f for _, f in GOLDEN["columns"]]
    assert layout.sheet_name == GOLDEN["sheet"]
    # The title above the header row, and the blank row under it.
    assert [[c.text for c in cells] for cells in layout.banner] == [[GOLDEN["title"]], []]
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
    unseen = unseen_letters(UNSEEN)[key]
    answer = answer_with(
        UNSEEN, **{letter_of(UNSEEN, "quantity"): None, unseen: {"field": "quantity"}}
    )
    view = asyncio.run(Bench.of(REPO, Recorded(raw=answer), (AN,)).draft(UNSEEN))
    assert view.status == "refused"
    assert ("header_not_in_template", "quantity") in [(p.code, p.field) for p in view.problems]


def test_a_header_only_a_hidden_cell_holds_is_refused() -> None:
    hidden = "D"  # `hidden_columns` puts it at index 3
    assert INJECTION["hidden_columns"][0]["at"] == 3
    answer = answer_with(
        INJECTION, **{letter_of(INJECTION, "quantity"): None, hidden: {"field": "quantity"}}
    )
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


B41: dict[str, Any] = next(g for g in _CASES["golden"] if g["id"] == "T-VI-B41")


def test_a_template_shaped_as_bravos_import_sales_order_is_drafted_whole() -> None:
    """Ticket 02: the title and group rows above row 3, 39 columns with
    "Delivery term", "Delivery mode" and "Destination" printed twice, a
    customer value and a fixed text: drafted at their places, ready."""
    view = asyncio.run(Bench.of(REPO, Recorded(raw=gold(B41)), (AN,)).draft(B41))
    assert view.status == "ready", view.problems
    layout = BravoUploadLayout.model_validate(view.document)
    assert [[(c.text, c.first, c.last) for c in cells] for cells in layout.banner] == [
        [("File import Sales order", 1, 39)],
        [("ĐẦU PHIẾU", 1, 18), ("CHI TIẾT", 19, 39)],
    ]
    assert [c.header for c in layout.columns] == [h for h, _ in B41["columns"]]
    by_place = [(c.field, c.customer, c.constant) for c in layout.columns]
    assert by_place[13] == (None, "delivery_term", None)
    assert by_place[36] == (None, None, None)  # the line-level "Delivery term" stays blank
    assert by_place[38] == (None, None, "XA")
    # The format the version in force has for the same field.
    assert layout.columns[26].number_format == "#,##0"
    # Every column left blank is named for the person to check.
    blank = sum(1 for _, s in B41["columns"] if s is None)
    assert [p.code for p in view.problems] == ["column_unmapped"] * blank


def test_a_value_the_rows_do_not_all_repeat_is_no_fixed_value() -> None:
    """Column J ("người lập") holds a different staff code on each row: a
    model taking one as the column's fixed value is refused."""
    answer = answer_with(B41, J={"constant": "NV-A"})
    view = asyncio.run(Bench.of(REPO, Recorded(raw=answer), (AN,)).draft(B41))
    assert view.status == "refused"
    assert [(p.code, p.ref) for p in view.problems if p.code != "column_unmapped"] == [
        ("constant_not_in_template", "J3")
    ]


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (None, "model_not_configured"),
        (Recorded(failure=ModelUnavailableError("down")), "model_unavailable"),
        (Recorded(raw={"po_no": "Số PO"}), "model_unavailable"),
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

    from dw_platform.testing.scanners import ScriptedScanner

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
