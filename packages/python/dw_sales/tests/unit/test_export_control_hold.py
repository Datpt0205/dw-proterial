"""Every mock order that fails export control is held until the export-control
PIC accepts it (the customer contract's acceptance row 3: 100% of the test
cases that do not meet the export-control conditions are held awaiting
approval, never confirmed automatically).

Which cases those are is read from the scenario source, the README's
"Messages" table (`readme_claims`), never typed here: a scenario added with
`missing_noc_esf` is covered the day it lands. Each is processed and walked
through the real services, runner and approval flow over in-memory stores
(`open_world`), as the API composes them, under the demo tenant's own rules,
to the last step before confirmation; confirmation is refused, naming the
finding, and goes through once the export-control PIC has accepted it.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest

from dw_kernel.errors import ConflictError
from dw_sales.adapters.mock.fixtures import DATA_DIR, MOCK_ROOT
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.domain.orders import (
    ALLOWED_DISPOSITIONS,
    DispositionKind,
    FindingCode,
    OrderCase,
    Severity,
)
from dw_sales.evals.graders import AN, CALLERS, DIEU, readme_claims
from dw_sales.evals.world import SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
NOC = "missing_noc_esf:-"
CONFIRMED_ON = date(2026, 11, 27)


def _held_scenarios() -> list[str]:
    claims = readme_claims((MOCK_ROOT / "README.md").read_text(encoding="utf-8"))
    return sorted(
        message_id
        for message_id, claim in claims.items()
        if (FindingCode.MISSING_NOC_ESF.value, None) in claim.findings
    )


HELD = _held_scenarios()


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


def test_the_scenario_source_has_orders_that_fail_export_control() -> None:
    # A coverage test over an empty list proves nothing.
    assert HELD


def test_the_rules_in_force_hold_confirmation_and_show_the_finding_as_blocking() -> None:
    """The platform's current rules and the demo tenant's own: `warn` holds
    confirmation until accepted (`block_confirmation` would never release),
    and the finding is an error, so the order reads as blocked."""
    platform = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
    tenant = load_tenant_order_rules(DATA_DIR / "policies")
    assert tenant is not None
    for rules in (platform.order_rules, tenant):
        assert rules.export_control_mode == "warn", rules.version
        assert rules.finding(FindingCode.MISSING_NOC_ESF).severity is Severity.ERROR, rules.version


async def _decide_all_but_export_control(world: World, case_id: uuid.UUID) -> None:
    """Every open finding but `missing_noc_esf` decided by An the way its
    code allows. A decision can run the checks again, so the case is read
    afresh after each one."""
    commands, context = world.services.order_commands, AN.context()
    for _ in range(50):
        case = world.order(case_id)
        finding = next((f for f in case.findings if f.is_open and f.key != NOC), None)
        if finding is None:
            return
        version = case.case_version
        if finding.code is FindingCode.VALUE_UNCERTAIN:
            assert finding.line_no is not None, f"no walk for {finding.key}"
            line = case.line(finding.line_no)
            name = sorted(case.flagged_fields(finding) - {c.field for c in line.corrections})[0]
            await commands.correct_value(
                context,
                case_id,
                finding.key,
                case_version=version,
                field=name,
                value=str(getattr(line.po_line, name)),
            )
        elif DispositionKind.ACCEPTED in ALLOWED_DISPOSITIONS[finding.code]:
            await commands.dispose(
                context,
                case_id,
                finding.key,
                case_version=version,
                disposition="accepted",
                reason="Đã kiểm tra với khách",
            )
        else:
            value = case.customer_code if finding.code is FindingCode.CUSTOMER_UNKNOWN else "1"
            await commands.dispose(
                context,
                case_id,
                finding.key,
                case_version=version,
                disposition="corrected_by_sales",
                value=value,
                source="PO gốc",
            )
    pytest.fail(f"the findings of {case_id} never settled")


async def _cross_checked(world: World, message_id: str) -> OrderCase:
    """The order the message opened, every other finding decided, prepared and
    entered in Bravo by An, cross-checked by Diệu, and PC's agreement recorded
    on each short line: nothing but `missing_noc_esf` stands before
    confirmation."""
    ((disposition, case),) = (await world.process_each(AN, [message_id])).values()
    assert isinstance(case, OrderCase), disposition
    await _decide_all_but_export_control(world, case.case_id)
    await world.walk_to_uploaded(AN, case.case_id)
    await world.cross_check(DIEU, case.case_id)
    short = {
        f.line_no
        for f in world.order(case.case_id).findings
        if f.code is FindingCode.REQUESTED_DATE_SHORT_LT and f.line_no is not None
    }
    for line_no in sorted(short):
        await world.services.order_commands.record_pc_date(
            AN.context(),
            case.case_id,
            line_no,
            case_version=world.order(case.case_id).case_version,
        )
    return world.order(case.case_id)


@pytest.mark.parametrize("message_id", HELD)
async def test_an_order_failing_export_control_is_held_until_the_export_control_pic_accepts(
    message_id: str,
) -> None:
    world = _world()
    crossed = await _cross_checked(world, message_id)
    finding = crossed.finding(NOC)
    assert (crossed.status.value, finding.is_open, finding.blocking) == (
        "cross_checked",
        True,
        True,
    )

    with pytest.raises(ConflictError, match="missing_noc_esf"):
        await world.confirm(AN, crossed.case_id, CONFIRMED_ON)
    held = world.order(crossed.case_id)
    assert (held.status, held.case_version) == (crossed.status, crossed.case_version)

    await world.services.order_commands.dispose(
        AN.context(),
        crossed.case_id,
        NOC,
        case_version=held.case_version,
        disposition="accepted",
        reason="Đã nhận NOC và ESF năm nay",
    )
    assert (await world.confirm(AN, crossed.case_id, CONFIRMED_ON)).status.value == "confirmed"
