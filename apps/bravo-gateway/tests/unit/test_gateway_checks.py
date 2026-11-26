"""Each of a write's checks refuses in a test of its own (ticket 63,
acceptance 2), and a write that passes them all is the client's own save."""

from __future__ import annotations

import base64
import dataclasses
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from gateway_fakes import (
    NOW,
    PIC,
    SET_DATE,
    SET_QUANTITY,
    TENANT,
    WORKSPACE,
    gateway,
    token,
)

from dw_bravo.approval_token import ApprovalTokenSigner
from dw_bravo.contract import CreateSalesOrder, SalesOrderLine, SetConfirmedDate
from dw_bravo_gateway.ports import BravoUser, ColumnRight, LedgerEntry
from dw_bravo_gateway.statements import SCREENS

pytestmark = pytest.mark.unit


async def test_a_write_that_passes_every_check_is_the_clients_own_save() -> None:
    gw = gateway()
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY, approval=approval))

    assert result.outcome == "written", result
    [batch] = gw.bravo.batches
    assert batch.context == "EDIT_BizDocSO|Edit".ljust(50) + "@2413@0@A01@2026"
    header, line = batch.statements
    # The header, then the line, each in the table's column order, holding
    # its rowversion, reading the row back: the client's statement.
    assert header.sql == (
        "UPDATE TOP (1) B30BizDoc SET [ModifiedBy]=@_ModifiedBy,[TotalQuantity]=@_TotalQuantity,"
        "[ModifiedAt]=DEFAULT WHERE Id=@_Original_Id AND timestamp=@_Original_timestamp;"
        "SELECT TOP (1) Id,BizDocId,CreatedAt,ModifiedAt,timestamp FROM B30BizDoc WHERE Id=@_Id;"
    )
    assert line.sql.startswith(
        "UPDATE TOP (1) B30BizDocDetailSO SET [Quantity9]=@_Quantity9,[Amount9]=@_Amount9,"
        "[ModifiedBy]=@_ModifiedBy,[ModifiedAt]=DEFAULT"
    )
    assert line.parameters["_Quantity9"] == Decimal(5)
    assert line.parameters["_Amount9"] == Decimal(10)  # the layout's rule, not the command
    assert line.parameters["_ModifiedBy"] == Decimal(2413)  # the PIC, from the token
    assert line.parameters["_Original_timestamp"] == "0x00000000000007D2"
    assert gw.ledger.entries[approval].status == "written"


# --------------------------------------------------------- 1: the token


async def test_a_bad_signature_is_refused() -> None:
    other = ApprovalTokenSigner(Ed25519PrivateKey.generate(), "k1")
    forged = other.sign(
        approval_id=uuid.uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        command=SET_DATE,
        bravo_user_id=2413,
        employee_code="NV001",
        now=NOW,
    )
    gw = gateway()

    result = await gw.pipeline.execute(SET_DATE, forged)

    assert (result.check, result.reason) == ("token", "bad_signature")
    assert gw.bravo.batches == []


async def test_content_changed_after_approval_is_refused() -> None:
    gw = gateway()
    changed = dataclasses.replace(SET_DATE, confirmed_date=date(2026, 12, 2))

    result = await gw.pipeline.execute(changed, token(SET_DATE))

    assert (result.check, result.reason) == ("token", "content_changed_since_approval")


async def test_an_approval_of_another_kind_is_refused() -> None:
    gw = gateway()

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_DATE))

    assert (result.check, result.reason) == ("token", "kind_not_approved")


async def test_an_expired_token_is_refused() -> None:
    gw = gateway()
    gw.pipeline.now = lambda: NOW + timedelta(hours=3)

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("token", "expired")


def _with_tenant_swapped(signed: str) -> str:
    body, signature = signed.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["tid"] = str(uuid.uuid4())
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{base64.urlsafe_b64encode(text).rstrip(b'=').decode()}.{signature}"


async def test_a_tenant_written_into_the_token_after_signing_is_refused() -> None:
    gw = gateway()

    result = await gw.pipeline.execute(SET_DATE, _with_tenant_swapped(token()))

    assert (result.check, result.reason) == ("token", "bad_signature")


# --------------------------------------- what the token alone decides


@pytest.mark.parametrize(
    "command",
    [
        CreateSalesOrder(
            case_ref="M01",
            doc_date=date(2026, 11, 21),
            currency_code="USD",
            customer_code="C1",
            po_customer="PO-1",
            lines=(
                SalesOrderLine(
                    po_line="1",
                    customer_description="x",
                    quantity=Decimal(1),
                    unit_price=Decimal(1),
                ),
            ),
        ),
    ],
    ids=["create_waits_on_03c"],
)
async def test_a_kind_not_yet_measured_is_refused_even_when_approved(command: object) -> None:
    gw = gateway()

    result = await gw.pipeline.execute(command, token(command))  # type: ignore[arg-type]

    assert result.check == "kind" and (result.reason or "").startswith("pending:")


@pytest.mark.parametrize("state", ["off", "paused"])
async def test_a_kind_off_for_the_tenant_or_paused_by_the_watch_is_refused(state: str) -> None:
    gw = gateway()
    gw.switches.state_ = state  # type: ignore[assignment]

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("switch", f"write_kind_{state}")
    assert gw.bravo.batches == []


async def test_a_repeated_approval_id_writes_once() -> None:
    gw = gateway()
    approval = uuid.uuid4()
    signed = token(SET_QUANTITY, approval=approval)

    first = await gw.pipeline.execute(SET_QUANTITY, signed)
    second = await gw.pipeline.execute(SET_QUANTITY, signed)

    assert first.outcome == "written"
    assert (second.outcome, second.reason) == ("already_written", "approval_already_written")
    assert len(gw.bravo.batches) == 1


@pytest.mark.parametrize("status", ["claimed", "in_doubt", "refused"])
async def test_an_approval_id_spent_otherwise_is_refused(status: str) -> None:
    gw = gateway()
    approval = uuid.uuid4()
    gw.ledger.entries[approval] = LedgerEntry(approval, status, "x", "y")  # type: ignore[arg-type]

    result = await gw.pipeline.execute(SET_DATE, token(approval=approval))

    assert (result.check, result.reason) == ("ledger", f"approval_already_{status}")


# -------------------------------------------------------- 2: identity


async def test_a_bravo_user_changed_since_the_approval_is_refused() -> None:
    gw = gateway()
    gw.directory.users = [dataclasses.replace(PIC, id=3000)]  # the account was re-created

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("identity", "bravo_user_changed_since_approval")


@pytest.mark.parametrize(
    ("users", "reason"),
    [
        ([dataclasses.replace(PIC, active=False)], "no_active_bravo_user_for_employee_code"),
        ([], "no_active_bravo_user_for_employee_code"),
        (
            [PIC, BravoUser(id=4000, user_name="dup", employee_code="NV001", active=True)],
            "several_active_bravo_users_for_employee_code",
        ),
    ],
    ids=["inactive", "none", "two"],
)
async def test_identity_must_be_one_active_user(users: list[BravoUser], reason: str) -> None:
    gw = gateway()
    gw.directory.users = users

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("identity", reason)


# ------------------------------------------------------------ 3: right


@pytest.mark.parametrize("answer", ["denied", "unknown"])
async def test_a_user_without_the_command_right_is_refused(answer: str) -> None:
    gw = gateway()
    gw.rights.command = answer  # type: ignore[assignment]

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("right", f"command_right_{answer}")


async def test_a_user_barred_from_the_column_they_would_type_is_refused() -> None:
    gw = gateway()
    gw.rights.columns = [ColumnRight("B30BizDocDetailSO", "EstimatedTimeDelivery", False, True)]

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("right", "no_right_on_EstimatedTimeDelivery")


# ------------------------------------------------------------ 4: rules


async def test_a_blocking_validator_refuses() -> None:
    gw = gateway()
    below_made = dataclasses.replace(SET_QUANTITY, quantity=Decimal(1))  # 2 were made

    result = await gw.pipeline.execute(below_made, token(below_made))

    assert (result.check, result.reason) == ("rules", "blocked: QtyNotBelowMade")
    assert gw.bravo.batches == []


async def test_a_warning_goes_back_with_the_write() -> None:
    gw = gateway()
    early = dataclasses.replace(SET_DATE, confirmed_date=date(2026, 11, 1))  # before DocDate

    result = await gw.pipeline.execute(early, token(early))

    assert result.outcome == "written" and result.warnings == ("Late",)


async def test_a_line_changed_since_the_approval_is_refused_before_anything_runs() -> None:
    gw = gateway()
    gw.bravo.document.lines[0]["timestamp"] = "0x00000000000009FF"

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("rules", "line_changed_since_approval")


# ------------------------------------------------------------- 5: lock


@pytest.mark.parametrize("answer", [1, None], ids=["on_a_cdo", "could_not_check"])
async def test_a_locked_line_is_refused(answer: int | None) -> None:
    gw = gateway()
    gw.bravo.document.prevent_edit = {"R20": answer}

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("lock", "line_locked_or_could_not_check")
    assert gw.bravo.batches == []


# ------------------------------------------------------------ 6: write


async def test_a_stale_timestamp_at_the_write_writes_nothing_and_spends_the_approval() -> None:
    from dw_bravo_gateway.ports import StaleRowError

    gw = gateway()
    gw.bravo.fail_with = StaleRowError("B30BizDocDetailSO")
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_DATE, token(approval=approval))

    assert (result.check, result.reason) == ("write", "row_changed_before_write")
    assert gw.ledger.entries[approval].status == "refused"


async def test_no_answer_after_sending_is_in_doubt_never_written() -> None:
    gw = gateway()
    gw.bravo.fail_with = ConnectionResetError()
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_DATE, token(approval=approval))

    assert result.outcome == "in_doubt"
    assert gw.ledger.entries[approval].status == "in_doubt"


async def test_a_read_back_that_differs_is_reported_column_by_column() -> None:
    gw = gateway()
    gw.bravo.tamper = {"Quantity9": Decimal(4)}  # a trigger changed what was written
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY, approval=approval))

    assert result.outcome == "written_with_differences"
    assert result.differences == ("Detail#0.Quantity9",)
    assert gw.ledger.entries[approval].status == "reconcile_failed"


async def test_the_unmeasured_context_of_a_save_refuses_before_the_approval_is_spent() -> None:
    gw = gateway()
    # A screen whose save has no traced word (a new screen before its trace).
    gw.pipeline.screens = {
        "EDIT_BizDocSO": dataclasses.replace(
            SCREENS["EDIT_BizDocSO"], context_event={"insert": "New"}
        )
    }
    approval = uuid.uuid4()

    result = await gw.pipeline.execute(SET_DATE, token(approval=approval))

    assert (result.check, result.reason) == (
        "write",
        "unmeasured: the client's context for this save",
    )
    assert approval not in gw.ledger.entries


async def test_bravo_not_answering_is_could_not_check() -> None:
    gw = gateway()
    gw.directory.down = True

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.outcome, result.reason) == ("refused", "bravo_unreachable_could_not_check")


def test_the_shipped_so_screen_saves_a_stored_so_as_the_client_does() -> None:
    # Traced 11-25/26 (ticket 70): an SO opened from the list saves as `Edit`;
    # one created in the window as `New`.
    assert dict(SCREENS["EDIT_BizDocSO"].context_event) == {"update": "Edit", "insert": "New"}


async def test_a_stored_sos_save_carries_the_clients_edit_context() -> None:
    gw = gateway()
    gw.pipeline.screens = dict(SCREENS)  # the shipped table, no test override

    result = await gw.pipeline.preview(SET_DATE, token())

    assert result.batch is not None, result
    assert result.batch.context.startswith("EDIT_BizDocSO|Edit")


async def test_a_confirmed_date_is_written_as_bravos_midnight_datetime() -> None:
    gw = gateway()

    result = await gw.pipeline.execute(SET_DATE, token())

    assert result.outcome == "written"
    line = gw.bravo.batches[0].statements[-1]
    assert str(line.parameters["_EstimatedTimeDelivery"]) == "2026-12-01 00:00:00"
    assert isinstance(SET_DATE, SetConfirmedDate)


async def test_a_blocking_validator_that_cannot_be_decided_refuses_like_a_block() -> None:
    gw = gateway()
    gw.bravo.document.lines[0]["Made"] = None  # what was produced is not known

    result = await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY))

    assert (result.check, result.reason) == ("rules", "undecided: QtyNotBelowMade")
    assert gw.bravo.batches == []


async def test_another_tenants_signed_approval_is_refused() -> None:
    gw = gateway()
    gw.pipeline.tenant_id = uuid.uuid4()  # this gateway's Bravo belongs to someone else

    result = await gw.pipeline.execute(SET_DATE, token())

    assert (result.check, result.reason) == ("token", "another_tenants_approval")
    assert gw.bravo.batches == []


async def test_a_documents_lock_is_gone_once_no_write_holds_it() -> None:
    import gc

    gw = gateway()
    await gw.pipeline.execute(SET_QUANTITY, token(SET_QUANTITY))
    gc.collect()

    assert len(gw.pipeline.pace._locks) == 0
