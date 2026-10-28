"""Export control, WIV-03-032 (2026-10-28): each result a person records, and
the orders it moves (`ScreenedCatalog`, `effective_compliance`)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_sales.application.malware import ScanVerdict
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Compliance
from dw_sales.domain.export_control import (
    Evidence,
    ScreeningRecord,
    ScreeningStep,
    effective_compliance,
)
from dw_sales.domain.orders import FindingCode, OrderCase
from dw_sales.evals.graders import AN, CALLERS, READER
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world
from dw_sales.testing.scanners import ScriptedScanner

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
PDF = b"%PDF-1.4\n% a scan\n%%EOF\n"
DAY = date(2026, 10, 1)
AT = datetime(2026, 10, 1, 3, tzinfo=UTC)
WHO = uuid.UUID(int=0xEC)


def _world(**options: object) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, **options)  # type: ignore[arg-type]


def _record(step: ScreeningStep, outcome: str, **fields: object) -> ScreeningRecord:
    return ScreeningRecord.model_validate(
        {
            "customer_code": "VLX",
            "step": step,
            "outcome": outcome,
            "checked_on": DAY,
            "recorded_by": WHO,
            "recorded_at": AT,
            **fields,
        }
    )


EVIDENCE = Evidence(
    file_id=uuid.UUID(int=1), sha256="a" * 64, content_type="application/pdf", size_bytes=10
)
BASE = Compliance(noc_confirmed=False, esf_fiscal_year=2025, denial_list_checked_on=None)


# ------------------------------------------------------------------ domain --


def test_results_move_compliance_and_never_loosen_a_hold() -> None:
    moved = effective_compliance(
        BASE,
        [
            _record(ScreeningStep.NOC, "received", evidence=EVIDENCE),
            _record(ScreeningStep.ESF, "approved", fiscal_year=2026, evidence=EVIDENCE),
            _record(ScreeningStep.DENIAL_LIST, "clear"),
        ],
    )
    assert (moved.noc_confirmed, moved.esf_fiscal_year, moved.denial_list_checked_on) == (
        True,
        2026,
        DAY,
    )
    held = effective_compliance(
        BASE,
        [
            _record(ScreeningStep.DENIAL_LIST, "match"),
            _record(ScreeningStep.RED_FLAG, "escalated", answers={"rf01": True}),
        ],
    )
    assert held.denial_list_match and held.red_flag_escalated
    # An older ESF does not take the year back.
    older = effective_compliance(
        BASE.model_copy(update={"esf_fiscal_year": 2027}),
        [_record(ScreeningStep.ESF, "approved", fiscal_year=2026, evidence=EVIDENCE)],
    )
    assert older.esf_fiscal_year == 2027


@pytest.mark.parametrize(
    "fields",
    [
        {"step": ScreeningStep.NOC, "outcome": "clear"},
        {"step": ScreeningStep.NOC, "outcome": "received"},  # no document
        {"step": ScreeningStep.ESF, "outcome": "approved", "evidence": EVIDENCE},  # no year
        {"step": ScreeningStep.DENIAL_LIST, "outcome": "clear", "fiscal_year": 2026},
        {"step": ScreeningStep.RED_FLAG, "outcome": "clear", "answers": {"rf01": True}},
        {"step": ScreeningStep.RED_FLAG, "outcome": "clear"},  # no answers
        {"step": ScreeningStep.DENIAL_LIST, "outcome": "clear", "answers": {"rf01": False}},
    ],
)
def test_a_result_that_contradicts_its_step_is_refused(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _record(**fields)  # type: ignore[arg-type]


# --------------------------------------------------- the orders it moves --


async def _order(world: World, message_id: str) -> OrderCase:
    ((_, case),) = (await world.process_each(AN, [message_id])).values()
    assert isinstance(case, OrderCase)
    return case


def _compliance(case: OrderCase) -> list[str]:
    return [f.actual for f in case.findings if f.code is FindingCode.MISSING_NOC_ESF]


async def test_a_noc_and_an_esf_recorded_here_clear_the_customers_next_order() -> None:
    world = _world()
    ec = world.services.export_control
    await ec.record_noc(
        AN.context(), "BRN", outcome="received", checked_on=DAY, note=None, evidence=PDF
    )
    await ec.record_esf(
        AN.context(), "BRN", fiscal_year=2026, approved_on=DAY, note=None, evidence=PDF
    )

    assert _compliance(await _order(world, "M03")) == []


async def test_a_denial_list_match_holds_the_customers_order() -> None:
    world = _world()
    await world.services.export_control.record_denial(
        AN.context(), "VLX", outcome="match", checked_on=DAY, note="tên trùng", evidence=None
    )

    (actual,) = _compliance(await _order(world, "M01"))
    assert "denial-list match" in actual


async def test_without_a_result_the_order_is_held_as_the_master_data_says() -> None:
    world = _world()
    (actual,) = _compliance(await _order(world, "M03"))
    assert actual.startswith("no NOC")


# ---------------------------------------------------------- the service --


async def test_the_overview_says_what_each_customer_still_needs() -> None:
    world = _world()
    overview = await world.services.export_control.overview(AN.context())
    brn = next(c for c in overview.customers if c.customer_code == "BRN")
    assert {"noc_missing", "esf_due", "red_flag_missing"} <= set(brn.needs)
    assert overview.sample  # the policy is a sample until Proterial's arrives


async def test_red_flag_answers_cover_the_policys_questions_and_escalate_on_a_yes() -> None:
    world = _world()
    ec = world.services.export_control
    detail = await ec.customer(AN.context(), "VLX")
    ids = [q.id for q in detail.red_flags]
    with pytest.raises(DomainError):
        await ec.record_red_flag(
            AN.context(), "VLX", answers={ids[0]: False}, checked_on=DAY, note=None
        )

    answers = dict.fromkeys(ids, False) | {ids[2]: True}
    view = await ec.record_red_flag(AN.context(), "VLX", answers=answers, checked_on=DAY, note=None)
    assert view.outcome == "escalated"
    summary = (await ec.customer(AN.context(), "VLX")).summary
    assert "red_flag_escalated" in summary.needs


async def test_every_result_is_audited_without_its_note() -> None:
    world = _world()
    await world.services.export_control.record_denial(
        AN.context(), "VLX", outcome="clear", checked_on=DAY, note="bí mật", evidence=None
    )
    (event,) = world.export_control.audit
    assert event.action == "sales.export_control.denial_list.clear"
    assert "bí mật" not in str(event.details)


async def test_a_document_backed_result_needs_its_document_scanned_clean() -> None:
    infected = ScriptedScanner({PDF: ScanVerdict.infected("Eicar")})
    world = _world(scanner=infected)
    ec = world.services.export_control
    with pytest.raises(DomainError) as missing:
        await ec.record_noc(
            AN.context(), "BRN", outcome="received", checked_on=DAY, note=None, evidence=None
        )
    assert missing.value.details["rule"] == "evidence_required"
    with pytest.raises(DomainError):  # not a PDF or a photo
        await ec.record_noc(
            AN.context(), "BRN", outcome="received", checked_on=DAY, note=None, evidence=b"PK\x03"
        )
    with pytest.raises(ConflictError):
        await ec.record_noc(
            AN.context(), "BRN", outcome="received", checked_on=DAY, note=None, evidence=PDF
        )
    assert world.export_control.held.get(ALPHA, {}) == {}


async def test_the_noc_document_is_served_back_as_stored() -> None:
    world = _world()
    ec = world.services.export_control
    await ec.record_noc(
        AN.context(), "BRN", outcome="received", checked_on=DAY, note=None, evidence=PDF
    )
    download = await ec.evidence(AN.context(), "BRN", ScreeningStep.NOC)
    assert download.data == PDF
    assert download.file_name == "noc-BRN.pdf"


async def test_recording_needs_the_export_control_permission_set() -> None:
    world = _world()
    with pytest.raises(PermissionDeniedError):
        await world.services.export_control.record_denial(
            READER.context(), "VLX", outcome="clear", checked_on=DAY, note=None, evidence=None
        )
    assert world.export_control.held.get(ALPHA, {}) == {}


async def test_an_unknown_customer_and_a_future_day_are_refused() -> None:
    world = _world()
    ec = world.services.export_control
    with pytest.raises(NotFoundError):
        await ec.record_denial(
            AN.context(), "ZZZ", outcome="clear", checked_on=DAY, note=None, evidence=None
        )
    with pytest.raises(DomainError):
        await ec.record_denial(
            AN.context(),
            "VLX",
            outcome="clear",
            checked_on=date(2099, 1, 1),
            note=None,
            evidence=None,
        )


async def test_another_workspaces_results_are_not_this_ones() -> None:
    world = _world()
    await world.services.export_control.record_denial(
        AN.context(), "VLX", outcome="match", checked_on=DAY, note=None, evidence=None
    )
    other = world.export_control(SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.uuid4())))
    async with other as work:
        assert await work.screenings.records() == []


async def test_the_noec_draft_is_written_to_the_customers_contacts_in_their_language() -> None:
    world = _world()
    download = await world.services.export_control.noec_draft(AN.context(), "VLX")
    text = download.data.decode("utf-8", "replace")
    assert download.file_name == "NOEC-VLX.eml"
    assert "NOC" in text
    # Drafting records nothing: the PIC records the NOEC once sent.
    assert world.export_control.held.get(ALPHA, {}) == {}


async def test_the_esf_form_names_each_approver_to_sign() -> None:
    world = _world()
    ec = world.services.export_control
    download = await ec.esf_form(AN.context(), "VLX", pdf=False)
    assert download.file_name.startswith("ESF-VLX-FY")
    detail = await ec.customer(AN.context(), "VLX")
    assert detail.esf_approvers
