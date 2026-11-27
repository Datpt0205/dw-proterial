"""Ticket 74: every save the gateway makes ends as the client's does, with
Bravo's business-process procedure, in the same transaction."""

from __future__ import annotations

import pytest
from gateway_fakes import SET_QUANTITY, gateway, token

from dw_bravo_gateway.adapters.sqlserver import bind_step
from dw_bravo_gateway.ports import ProcedureStep
from dw_bravo_gateway.statements import PROCESS_PROCEDURE, process_step

pytestmark = pytest.mark.unit


async def test_a_write_ends_with_the_documents_process_step() -> None:
    gw = gateway()

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY))

    assert result.outcome == "written", result
    [batch] = gw.bravo.batches
    assert batch.steps == (
        ProcedureStep(
            PROCESS_PROCEDURE,
            {
                "_BizDocId": "D10",
                "_BizProcessGroupUnique": None,
                "_BranchCode": "A01",
                "_DocCode": "SO",
            },
        ),
    )


async def test_the_preview_shows_the_step_it_would_run() -> None:
    gw = gateway()

    preview = await gw.pipeline.preview(SET_QUANTITY, token(SET_QUANTITY))

    assert preview.batch is not None
    assert [s.name for s in preview.batch.steps] == [PROCESS_PROCEDURE]
    assert gw.bravo.batches == []


def test_a_document_without_its_keys_has_no_step() -> None:
    from dw_bravo_gateway.statements import UnmeasuredError

    with pytest.raises(UnmeasuredError):
        process_step("EDIT_BizDocSO", {"BizDocId": "D10"})


def test_the_step_is_bound_by_position_in_the_clients_argument_order() -> None:
    sql, values = bind_step(process_step("EDIT_BizDocSO", {"BizDocId": "D10", "BranchCode": "A01"}))

    assert sql == (
        "EXEC dbo.usp_B30BizDocProcess_CreateProcess "
        "@_BizDocId=?,@_BizProcessGroupUnique=?,@_BranchCode=?,@_DocCode=?;"
    )
    assert values == ("D10", None, "A01", "SO")


def test_no_other_procedure_is_run_by_the_write_login() -> None:
    with pytest.raises(ValueError, match="not a procedure a save runs"):
        bind_step(ProcedureStep("usp_anything_else", {}))
