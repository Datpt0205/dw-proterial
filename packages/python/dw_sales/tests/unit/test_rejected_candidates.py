"""Ticket 44 follow-up, "Không phải mã này": Sales rejects the candidates a
model's reading proposed for a line. The line is unmapped, a code for Sales
to type, keeping nothing of the reading; the rejection is a labelled case,
nothing kept; who may, on which version, and which lines may be rejected.

The case's rule by hand (`OrderCase.reject_candidates`), the command over the
in-memory world (`dw_sales.evals.world`) on M05 (line 1 ambiguous, line 2 one
candidate) as `test_labelled_cases` reads it with a model's reading.
"""

from __future__ import annotations

import uuid

import pytest

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import WorkspaceId
from dw_sales.application.ports import SalesScope
from dw_sales.domain.labelled_cases import mapping_label
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import (
    FindingCode,
    LineCheck,
    LineMapping,
    MappingStatus,
    OrderCase,
)
from dw_sales.evals.graders import AN, READER
from dw_sales.evals.world import ALPHA, BETA, World

from .test_activity import _reading
from .test_labelled_cases import AT, _confirm_code, _labels, _m05
from .test_orders import AN as PIC
from .test_orders import RULES, T0, _finding, _line, _review

pytestmark = pytest.mark.unit

_UNMAPPED = LineMapping(status=MappingStatus.UNMAPPED)


async def _reject(
    world: World, case: OrderCase, line_no: int, *, version: int | None = None
) -> None:
    await world.services.order_commands.reject_candidates(
        AN.context(),
        case.case_id,
        line_no,
        case_version=world.order(case.case_id).case_version if version is None else version,
    )


# --------------------------------------------------------- the case's rule --


def _model_read(line_no: int, mapping: LineMapping) -> OrderCase:
    line = _line(line_no, mapping)
    read = line.model_copy(
        update={"basis": line.basis.model_copy(update={"description_reading": _reading("read")})}
    )
    code = (
        FindingCode.CODE_AMBIGUOUS
        if mapping.status is MappingStatus.AMBIGUOUS
        else FindingCode.QUOTATION_MISSING
    )
    return _review(_finding(code, line_no), lines=(read, _line(2)))


def _unmapped_check(line_no: int) -> LineCheck:
    return LineCheck(
        line=_line(line_no, _UNMAPPED), findings=(_finding(FindingCode.CODE_UNMAPPED, line_no),)
    )


def test_a_model_read_candidate_rejected_leaves_the_line_unmapped_with_its_finding() -> None:
    one = LineMapping(status=MappingStatus.CANDIDATE, candidates=("CB-2005",))
    case = _model_read(1, one)

    rejected = case.reject_candidates(1, _unmapped_check(1))

    line = rejected.line(1)
    assert line.mapping == _UNMAPPED
    assert line.basis.description_reading is None and line.basis.item is None
    # The candidate's item finding is gone; the line now asks for a code.
    assert [f.key for f in rejected.findings] == ["code_unmapped:1"]
    assert rejected.case_version == case.case_version + 1
    # A code the item master holds is then typed, as on any unmapped line.
    typed = rejected.confirm_mapping(1, "CB-2009", PIC, T0, LineCheck(line=_line(1, _m("CB-2009"))))
    assert typed.line(1).mapping.hand_entered


def _m(code: str) -> LineMapping:
    return LineMapping(status=MappingStatus.EXACT, prv_code=code)


def test_several_candidates_are_rejected_together() -> None:
    several = LineMapping(status=MappingStatus.AMBIGUOUS, candidates=("CB-2001", "CB-2002"))

    rejected = _model_read(1, several).reject_candidates(1, _unmapped_check(1))

    assert rejected.line(1).mapping == _UNMAPPED
    assert [f.key for f in rejected.findings] == ["code_unmapped:1"]


def test_only_a_model_readings_unconfirmed_candidates_are_rejected() -> None:
    one = LineMapping(status=MappingStatus.CANDIDATE, candidates=("CB-2005",))
    # DW1's own vocabulary proposed it: no model reading to reject.
    by_code = _review(lines=(_line(1, one), _line(2)))
    with pytest.raises(ConflictError, match="model's reading"):
        by_code.reject_candidates(1, _unmapped_check(1))
    # The convert list's code, and a code already confirmed, hold no candidates.
    with pytest.raises(ConflictError, match="no candidates"):
        by_code.reject_candidates(2, _unmapped_check(2))
    confirmed = _model_read(1, one).confirm_mapping(
        1, "CB-2005", PIC, T0, LineCheck(line=_line(1, _m("CB-2005")))
    )
    with pytest.raises(ConflictError, match="no candidates"):
        confirmed.reject_candidates(1, _unmapped_check(1))


def test_the_line_must_be_checked_again_as_unmapped_without_the_reading() -> None:
    one = LineMapping(status=MappingStatus.CANDIDATE, candidates=("CB-2005",))
    case = _model_read(1, one)

    with pytest.raises(DomainError, match="with a mapping"):
        case.reject_candidates(1, LineCheck(line=_line(1, one)))
    still_read = case.line(1).model_copy(update={"mapping": _UNMAPPED})
    still_read = still_read.model_copy(
        update={"basis": still_read.basis.model_copy(update={"item": None, "candidates": ()})}
    )
    with pytest.raises(DomainError, match="with a mapping"):
        case.reject_candidates(1, LineCheck(line=still_read))
    other_rules = _finding(FindingCode.CODE_UNMAPPED, 1).model_copy(
        update={"rule_version": RULES.replace("1.13.0", "1.14.0")}
    )
    with pytest.raises(ConflictError, match="other rules"):
        case.reject_candidates(1, LineCheck(line=_line(1, _UNMAPPED), findings=(other_rules,)))


# --------------------------------------------------------------- the label --


async def test_the_rejection_label_keeps_nothing_and_names_the_proposal() -> None:
    _, case = await _m05(model_read=True)
    ids = iter([uuid.UUID(int=7)])

    label = mapping_label(case, 1, None, new_id=lambda: next(ids), at=AT, by=AN.user_id)

    assert label is not None
    assert (label.verdict, label.proposed, label.kept) == (
        "rejected",
        ["CB-2001", "CB-2002"],
        None,
    )


# ------------------------------------------------------------- the command --


async def test_rejecting_writes_one_rejected_case_and_the_typed_code_labels_nothing() -> None:
    world, case = await _m05(model_read=True)

    await _reject(world, case, 2)

    line = world.order(case.case_id).line(2)
    assert line.mapping == _UNMAPPED
    assert line.basis.description_reading is None
    (label,) = _labels(world)
    assert (label.step, label.verdict, label.proposed, label.kept, label.line_no) == (
        ModelStep.DESCRIPTION_ATTRIBUTES,
        "rejected",
        ["CB-2005"],
        None,
        2,
    )
    assert label.decided_by == AN.user_id
    event = world.store.state(ALPHA).events[-1]
    assert (event.action, event.actor_kind) == ("order.mapping_rejected", "user")
    audit = world.audit()[-1]
    assert (audit.action, audit.actor_id.value) == ("sales.order.mapping_rejected", AN.user_id)
    # The code then typed is a decision on no model's proposal: one case only.
    await _confirm_code(world, case, 2, "CB-2006")
    assert len(_labels(world)) == 1
    assert world.order(case.case_id).line(2).mapping.hand_entered


async def test_a_caller_without_the_scope_another_version_or_workspace_changes_nothing() -> None:
    world, case = await _m05(model_read=True)

    with pytest.raises(PermissionDeniedError):
        await world.services.order_commands.reject_candidates(
            READER.context(), case.case_id, 2, case_version=case.case_version
        )
    with pytest.raises(ConflictError):
        await _reject(world, case, 2, version=case.case_version - 1)
    other_workspace = SalesScope(ALPHA.tenant_id, WorkspaceId(uuid.UUID(int=0xA1FC)))
    for scope in (BETA, other_workspace):
        with pytest.raises(NotFoundError):
            await world.services.order_commands.reject_candidates(
                AN.context(scope), case.case_id, 2, case_version=case.case_version
            )

    assert _labels(world) == []
    assert world.order(case.case_id) == case


async def test_a_line_no_model_read_is_not_rejected_and_labels_nothing() -> None:
    world, case = await _m05(model_read=False)

    with pytest.raises(ConflictError, match="model's reading"):
        await _reject(world, case, 2)

    assert _labels(world) == []
    assert world.order(case.case_id).line(2).mapping.status is MappingStatus.CANDIDATE
