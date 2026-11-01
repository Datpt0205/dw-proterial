"""DW02 function 4: one draft order per chosen supplier and the Bravo import
file, drawn from the stamped layout. Over the in-memory world."""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.domain.cases import CaseStatus
from dw_purchasing.domain.orders import BravoPoLayout
from dw_purchasing.domain.sourcing import Choice
from dw_purchasing.testing.world import ALPHA, BETA, World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURES = REPO / "evals/fixtures/cases"
INTAKE = json.loads((FIXTURES / "purchasing_pr_intake.json").read_text(encoding="utf-8"))
SOURCING = json.loads((FIXTURES / "purchasing_sourcing.json").read_text(encoding="utf-8"))
HEAD = uuid.UUID(int=0x4EAD)
ONE = {"header": "A", "field": "po_ref"}
CHOICES = (
    Choice(line_no=1, supplier_code="KIMURA"),
    Choice(line_no=2, supplier_code="BAOHO"),
    Choice(line_no=3, supplier_code="ANPHAT"),
)


def _world() -> World:
    world = open_world(REPO, INTAKE["answers"])
    world.model.by_schema = {
        "ModelOffer": SOURCING["answers"],
        "RfqWording": {"PR-2611-004": SOURCING["rfq_words"]["good"]},
    }
    return world


async def _version(world: World, case_id: uuid.UUID) -> int:
    return (await world.service.case(caller(), case_id)).case_version


async def _chosen(world: World) -> uuid.UUID:
    item = await world.service.read_mail(caller(), "P01")
    case_id = item.case_id
    assert case_id is not None
    await world.approvals.submit(caller(), case_id, case_version=1)
    case = await world.service.case(caller(), case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await world.sourcing.draft_rfq(caller(), case_id, case_version=3)
    for message_id in ("Q01", "Q02", "Q03"):
        await world.sourcing.read_offer_mail(
            caller(), case_id, message_id, case_version=await _version(world, case_id)
        )
    await world.sourcing.select(
        caller(), case_id, CHOICES, case_version=await _version(world, case_id)
    )
    return case_id


async def test_one_order_per_chosen_supplier_at_the_chosen_prices() -> None:
    world = _world()
    case_id = await _chosen(world)
    version = await _version(world, case_id)
    change = await world.orders.draft(caller(), case_id, case_version=version)

    case = await world.service.case(caller(), case_id)
    assert change.status is CaseStatus.PO_DRAFTED and case.po is not None
    orders = {o.supplier_code: o for o in case.po.orders}
    assert {code: (o.po_ref, o.total) for code, o in orders.items()} == {
        "ANPHAT": ("PR-2611-004-01", Decimal(4_500_000)),
        "BAOHO": ("PR-2611-004-02", Decimal(4_900_000)),
        "KIMURA": ("PR-2611-004-03", Decimal(4_800_000)),
    }
    kimura = orders["KIMURA"]
    assert kimura.supplier_name == "Kimura Tools Việt Nam"
    assert [(line.line_no, line.unit_price, line.need_by) for line in kimura.lines] == [
        (1, Decimal(1_200_000), date(2026, 11, 20))
    ]
    from dw_purchasing.adapters.policy_files import PolicyFiles

    assert case.po.rules_ref == PolicyFiles.load(REPO / "configs/policies").current().ref
    assert world.store.rows(*ALPHA).audit[-1].action == "purchasing.po.drafted"


async def test_the_bravo_file_has_the_layouts_columns_and_a_row_per_order_line() -> None:
    world = _world()
    case_id = await _chosen(world)
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    download = await world.orders.bravo_file(caller(), case_id)

    sheet = load_workbook(io.BytesIO(download.data))["PO"]
    rows = [[c.value for c in row] for row in sheet.iter_rows()]
    assert rows[0][:4] == ["Số PO DW2", "Ngày đặt hàng", "Mã NCC", "Tên NCC"]
    assert len(rows) == 4  # the header and three order lines
    first = dict(zip(rows[0], rows[1], strict=True))
    assert (first["Số PO DW2"], first["Mã vật tư"], first["Số lượng"]) == (
        "PR-2611-004-01",
        "BK-1700",
        120,
    )
    assert first["Đơn giá"] == 37500 and first["Mã ngân sách"] == "CC-PROD-01"
    assert sheet.cell(row=2, column=2).number_format == "dd/mm/yyyy"
    again = await world.orders.bravo_file(caller(), case_id)
    assert again.data == download.data  # the stamp, drawn again


async def test_the_file_is_drawn_from_the_stamped_layout_not_the_rules_in_force() -> None:
    world = _world()
    case_id = await _chosen(world)
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    before = (await world.orders.bravo_file(caller(), case_id)).data
    # The tenant changes its Bravo layout afterwards.
    from dw_purchasing.adapters.policy_files import PolicyFiles

    current = PolicyFiles.load(REPO / "configs/policies").current()
    changed = current.model_dump(mode="json")
    changed["policy_version"] = "9.3.0"
    changed["bravo_po"]["columns"] = [{"header": "Chỉ một cột", "field": "po_ref"}]
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = changed
    assert (await world.orders.bravo_file(caller(), case_id)).data == before


async def test_a_description_that_reads_like_a_formula_stays_text_in_the_file() -> None:
    world = _world()
    case_id = await _chosen(world)
    case = await world.service.case(caller(), case_id)
    lines = list(case.request.lines)
    lines[0] = lines[0].model_copy(update={"description": '=HYPERLINK("http://x","bấm")'})
    stored = world.store.scopes[ALPHA]
    stored.cases[case_id] = case.model_copy(
        update={"request": case.request.model_copy(update={"lines": tuple(lines)})}
    )
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    data = (await world.orders.bravo_file(caller(), case_id)).data
    sheet = load_workbook(io.BytesIO(data))["PO"]
    cells = [c for row in sheet.iter_rows() for c in row if isinstance(c.value, str)]
    formula = next(c for c in cells if "HYPERLINK" in str(c.value))
    assert formula.data_type == "s" and formula.quotePrefix


async def test_orders_are_drafted_only_after_a_choice_by_who_may_and_once() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    with pytest.raises(ConflictError):  # nothing chosen yet
        await world.orders.draft(caller(), item.case_id, case_version=1)
    case_id = await _chosen(_w := _world())
    version = await _version(_w, case_id)
    no_scope = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await _w.orders.draft(no_scope, case_id, case_version=version)
    with pytest.raises(PermissionDeniedError):
        await _w.orders.bravo_file(no_scope, case_id)
    with pytest.raises(ConflictError):  # no draft to export yet
        await _w.orders.bravo_file(caller(), case_id)
    with pytest.raises(ConflictError):
        await _w.orders.draft(caller(), case_id, case_version=version - 1)
    await _w.orders.draft(caller(), case_id, case_version=version)
    with pytest.raises(ConflictError):
        await _w.orders.draft(caller(), case_id, case_version=version + 1)


async def test_another_tenant_can_neither_draft_nor_download() -> None:
    world = _world()
    case_id = await _chosen(world)
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    with pytest.raises(NotFoundError):
        await world.orders.bravo_file(caller(BETA), case_id)
    with pytest.raises(NotFoundError):
        await world.orders.draft(caller(BETA), case_id, case_version=9)


async def test_rules_without_a_bravo_layout_draft_nothing() -> None:
    world = _world()
    case_id = await _chosen(world)
    from dw_purchasing.adapters.policy_files import PolicyFiles

    current = PolicyFiles.load(REPO / "configs/policies").current()
    without: dict[str, Any] = current.model_dump(mode="json")
    without["policy_version"], without["bravo_po"] = "9.3.1", None
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = without
    with pytest.raises(ConflictError) as refused:
        await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    assert refused.value.details["rule"] == "no_layout"


@pytest.mark.parametrize(
    "layout",
    [
        {"sheet": "PO", "date_format": "dd/mm/yyyy", "columns": []},
        {
            "sheet": "P/O",
            "date_format": "dd/mm/yyyy",
            "columns": [{"header": "A", "field": "po_ref"}],
        },
        {
            "sheet": "PO",
            "date_format": "dd/mm/yyyy",
            "columns": [{"header": "A", "field": "price_we_like"}],
        },
        {
            "sheet": "PO",
            "date_format": "dd/mm/yyyy",
            "columns": [{"header": "A", "field": "po_ref"}, {"header": "A", "field": "pr_no"}],
        },
    ],
    ids=["no-columns", "bad-sheet-name", "unknown-field", "repeated-header"],
)
def test_a_layout_a_tenant_writes_is_held_to_its_shape(layout: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BravoPoLayout.model_validate(layout)


async def test_each_order_line_is_priced_at_the_offer_chosen_not_the_first_recorded() -> None:
    world = _world()
    case_id = await _chosen(world)
    # Choose again: ANPHAT, not KIMURA (whose offer was recorded first), for line 1.
    stored = world.store.scopes[ALPHA]
    case = stored.cases[case_id]
    assert case.selection is not None
    choices = (Choice(line_no=1, supplier_code="ANPHAT"), *CHOICES[1:])
    stored.cases[case_id] = case.model_copy(
        update={
            "selection": case.selection.model_copy(
                update={"choices": choices, "total": Decimal(5_160_000 + 4_900_000 + 4_500_000)}
            )
        }
    )
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    drafted = await world.service.case(caller(), case_id)
    assert drafted.po is not None
    (anphat,) = (o for o in drafted.po.orders if o.supplier_code == "ANPHAT")
    assert [(line.line_no, line.unit_price) for line in anphat.lines] == [
        (1, Decimal(1_290_000)),
        (3, Decimal(37_500)),
    ]


def test_the_same_rows_write_the_same_bytes_a_second_later() -> None:
    import time

    from dw_purchasing.adapters.bravo_file import BravoFile

    at = datetime(2026, 11, 3, 2, 0, tzinfo=UTC)
    rows: list[list[Any]] = [["Số PO"], ["PR-1-01"]]
    first = BravoFile().write("PO", rows, date_format="dd/mm/yyyy", at=at)
    time.sleep(1.1)  # openpyxl dates the workbook at save
    assert BravoFile().write("PO", rows, date_format="dd/mm/yyyy", at=at) == first


async def test_a_case_holds_its_orders_in_the_state_that_drafted_them_only() -> None:
    world = _world()
    case_id = await _chosen(world)
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    case = await world.service.case(caller(), case_id)
    with pytest.raises(ValidationError):
        type(case).model_validate({**case.model_dump(), "status": CaseStatus.SUPPLIER_SELECTED})


async def test_nothing_is_drafted_for_a_supplier_gone_or_a_total_that_moved() -> None:
    import dataclasses

    from dw_purchasing.testing.eval_graders import _Fixed

    world = _world()
    case_id = await _chosen(world)
    version = await _version(world, case_id)
    master = await world.orders.master.for_context(caller())
    gone = master.model_copy(
        update={"suppliers": tuple(s for s in master.suppliers if s.code != "BAOHO")}
    )
    orders = dataclasses.replace(world.orders, master=_Fixed(gone))
    with pytest.raises(ConflictError) as refused:
        await orders.draft(caller(), case_id, case_version=version)
    assert refused.value.details["rule"] == "supplier_gone"

    stored = world.store.scopes[ALPHA]
    case = stored.cases[case_id]
    assert case.selection is not None
    stored.cases[case_id] = case.model_copy(
        update={"selection": case.selection.model_copy(update={"total": Decimal(1)})}
    )
    with pytest.raises(ConflictError) as moved:
        await world.orders.draft(caller(), case_id, case_version=version)
    assert moved.value.details["rule"] == "total_mismatch"


async def test_a_deployed_dw2_drafts_no_order_with_the_platforms_stand_in_layout() -> None:
    """Rules 1.4.0 mark the shipped Bravo layout `mock`: a deployed profile
    refuses to draft with it, so no buyer imports a file the company's Bravo
    was never set up for. A tenant layout of its own drafts as before."""
    import dataclasses

    from dw_purchasing.adapters.policy_files import PolicyFiles

    world = _world()
    case_id = await _chosen(world)
    deployed = dataclasses.replace(world.orders, deployed=True)
    version = await _version(world, case_id)
    with pytest.raises(ConflictError) as refused:
        await deployed.draft(caller(), case_id, case_version=version)
    assert refused.value.details["rule"] == "mock_layout"
    own: dict[str, Any] = (
        PolicyFiles.load(REPO / "configs/policies").current().model_dump(mode="json")
    )
    own["policy_version"] = "9.4.0"
    own["bravo_po"]["mock"] = False
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = own
    change = await deployed.draft(caller(), case_id, case_version=version)
    assert change.status.value == "po_drafted"
