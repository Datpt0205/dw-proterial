"""The gateway's contract, as Sales' application asks for it (ticket 53).

`dw_bravo.contract` owns the typed commands and their hash, and
`dw_bravo.approval_token` the token; a context reaches both from its
adapters only (import-linter). `BravoContract` builds a line's command from
the change and Bravo's row and reads a stored one back; `ContractSigner`
signs the token for a stored command.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError

from dw_bravo.approval_token import ApprovalTokenSigner
from dw_bravo.contract import (
    WRITE_KINDS,
    BravoTarget,
    CancelLine,
    ContractError,
    LineRef,
    SetConfirmedDate,
    SetQuantity,
    WriteCommand,
    canonical_json,
    content_hash,
)
from dw_kernel.errors import ConflictError
from dw_sales.application.bravo_line_writes import (
    AnyChange,
    BravoSo,
    BravoSoLine,
    CancelChange,
    ConfirmedDateChange,
    PreparedWrite,
)


def _key(command: object) -> str:
    return f"{type(command).kind}@{type(command).version}"  # type: ignore[attr-defined]


def command_of(kind: str, content: dict[str, Any]) -> WriteCommand:
    """A stored command read back into its type, or a refusal."""
    write_kind = WRITE_KINDS.get(kind)
    if write_kind is None:
        raise ConflictError("lệnh ghi Bravo không còn là loại gateway nhận", details={"kind": kind})
    try:
        command: WriteCommand = TypeAdapter(write_kind.command).validate_python(content)
    except (ValidationError, ContractError):
        raise ConflictError(
            "lệnh ghi Bravo đã lưu không đọc lại được", details={"kind": kind}
        ) from None
    return command


class BravoContract:
    """`BravoCommandsPort`."""

    def prepare(self, change: AnyChange, so: BravoSo, line: BravoSoLine) -> PreparedWrite:
        ref = LineRef(so_id=so.so_id, line_id=line.line_id, line_rowversion=line.rowversion)
        command: WriteCommand
        if isinstance(change, ConfirmedDateChange):
            command = SetConfirmedDate(line=ref, confirmed_date=change.value)
        elif isinstance(change, CancelChange):
            command = CancelLine(line=ref, reason=change.reason)
        else:
            command = SetQuantity(line=ref, quantity=change.value)
        kind = _key(command)
        content: dict[str, Any] = json.loads(canonical_json(command))["content"]
        return PreparedWrite(kind, content, content_hash(command), WRITE_KINDS[kind].pending)

    def hash_of(self, kind: str, content: dict[str, Any]) -> str:
        return content_hash(command_of(kind, content))


@dataclass(frozen=True)
class ContractSigner:
    """`ApprovalSignerPort` over the key the decision signs with."""

    signer: ApprovalTokenSigner

    def sign(
        self,
        *,
        approval_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        kind: str,
        content: dict[str, Any],
        bravo_user_id: int,
        employee_code: str,
        target: BravoTarget,
        now: datetime,
    ) -> str:
        return self.signer.sign(
            approval_id=approval_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            command=command_of(kind, content),
            bravo_user_id=bravo_user_id,
            employee_code=employee_code,
            target=target,
            now=now,
        )
