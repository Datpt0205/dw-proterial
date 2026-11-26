"""Ticket 71: cancelling an SO line as a person does it on the SO screen.

The order of what is typed, the reason, a line of a split group, and how a
NULL reaches Bravo; the client's own statement for a traced cancel is
`test_gateway_trace_replay.test_a_traced_cancel_is_the_clients_own_statement`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from gateway_fakes import LINE, gateway, token

from dw_bravo.contract import CancelLine, ContractError
from dw_bravo_gateway.pipeline import Edit, typed_edits
from dw_bravo_gateway.statements import render_update

pytestmark = pytest.mark.unit

CANCEL = CancelLine(line=LINE, reason="Khách hủy dòng")


def test_a_cancel_is_typed_in_the_order_the_screen_allows() -> None:
    # The quantity opens for typing only once "Order status" is set, and the
    # cancelled price is taken before the zero quantity resets the price.
    assert typed_edits(CANCEL) == [
        Edit("Detail", "IsCancel", "Cancel"),
        Edit("Detail", "CancelRemark", "Khách hủy dòng"),
        Edit("Detail", "Quantity9", Decimal(0)),
    ]


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_cancel_without_its_reason_is_not_a_command(reason: str) -> None:
    with pytest.raises(ContractError, match="reason"):
        CancelLine(line=LINE, reason=reason)


def test_a_null_is_written_as_the_columns_default_as_the_client_does() -> None:
    statement = render_update(
        "B30BizDocDetailSO",
        {"Quantity9": Decimal(0), "OriginalUnitCost": None},
        ["Id", "Quantity9", "OriginalUnitCost"],
        row_id=20,
        rowversion="0x01",
        read_back_key="RowId",
    )
    assert "[Quantity9]=@_Quantity9,[OriginalUnitCost]=DEFAULT," in statement.sql
    assert "_OriginalUnitCost" not in statement.parameters


async def test_a_cancel_writes_the_screens_own_columns() -> None:
    gw = gateway()
    gw.bravo.document.lines[0]["Made"] = Decimal(0)

    result = await gw.pipeline.execute(CANCEL, token(CANCEL))

    assert result.outcome == "written", result
    [batch] = gw.bravo.batches
    line = next(s for s in batch.statements if s.table == "B30BizDocDetailSO")
    assert line.parameters["_IsCancel"] == "Cancel"
    assert line.parameters["_CancelRemark"] == "Khách hủy dòng"
    assert line.parameters["_Quantity9"] == Decimal(0)
    assert line.parameters["_Amount9"] == Decimal(0)  # the layout's rule


async def test_a_cancel_of_a_split_groups_line_is_refused_before_the_approval_is_spent() -> None:
    gw = gateway()
    gw.bravo.document.lines[0]["Divide"] = Decimal(1)
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(CANCEL, token(CANCEL, approval=approval))

    assert (result.check, result.reason) == ("rules", "unmeasured: a cancel of a split line")
    assert approval not in gw.ledger.entries
    assert gw.bravo.batches == []
