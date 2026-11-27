"""What the gateway keeps in DW's PostgreSQL: the ledger, and the switches.

Connected as `dw_app`, which does not bypass RLS. Every transaction binds
the tenant and workspace the verified approval token names
(`dw_platform`'s `tenant_session`, `set_config(..., true)`), so a pooled
connection carries nothing into the next one and a token for one tenant
reaches no other's rows (CLAUDE.md, "A second language", items 1-2, which
hold for a second process too).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_bravo.approval_token import ApprovalClaims
from dw_bravo.contract import BravoTarget
from dw_bravo_gateway.ports import LedgerEntry, LedgerStatus, SwitchState
from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.rule_versions import RuleVersion

_FIND = sa.text(
    "SELECT approval_id, status, kind, content_hash, detail FROM bravo.write_ledger"
    " WHERE approval_id = :approval_id"
)
_CLAIM = sa.text(
    "INSERT INTO bravo.write_ledger"
    " (tenant_id, workspace_id, approval_id, kind, content_hash, bravo_user_id, target,"
    "  status, claimed_at)"
    " VALUES (:tenant_id, :workspace_id, :approval_id, :kind, :content_hash, :bravo_user_id,"
    "  :target, 'claimed', :now)"
    " ON CONFLICT (tenant_id, approval_id) DO NOTHING"
)
_SETTLE = sa.text(
    "UPDATE bravo.write_ledger SET status = :status, detail = CAST(:detail AS jsonb),"
    " settled_at = :now WHERE approval_id = :approval_id AND status = 'claimed'"
)


def _scope(claims: ApprovalClaims) -> TenantScope:
    return TenantScope(tenant_id=claims.tenant_id, workspace_id=claims.workspace_id)


@dataclass
class SqlLedger:
    """`Ledger` over `bravo.write_ledger`: an approval id is claimed once."""

    session_factory: async_sessionmaker[AsyncSession]

    async def find(self, claims: ApprovalClaims) -> LedgerEntry | None:
        async with tenant_session(self.session_factory, _scope(claims)) as session:
            row = (
                (await session.execute(_FIND, {"approval_id": claims.approval_id}))
                .mappings()
                .first()
            )
        if row is None:
            return None
        return LedgerEntry(
            approval_id=row["approval_id"],
            status=row["status"],
            kind=row["kind"],
            content_hash=row["content_hash"],
            detail=dict(row["detail"]),
        )

    async def claim(self, claims: ApprovalClaims) -> bool:
        async with tenant_session(self.session_factory, _scope(claims)) as session:
            result = await session.execute(
                _CLAIM,
                {
                    "tenant_id": claims.tenant_id,
                    "workspace_id": claims.workspace_id,
                    "approval_id": claims.approval_id,
                    "kind": claims.kind,
                    "content_hash": claims.content_hash,
                    "bravo_user_id": claims.bravo_user_id,
                    "target": claims.target,
                    "now": datetime.now(UTC),
                },
            )
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def settle(
        self, claims: ApprovalClaims, status: LedgerStatus, detail: Mapping[str, object]
    ) -> None:
        async with tenant_session(self.session_factory, _scope(claims)) as session:
            result = await session.execute(
                _SETTLE,
                {
                    "approval_id": claims.approval_id,
                    "status": status,
                    "detail": json.dumps(dict(detail)),
                    "now": datetime.now(UTC),
                },
            )
        if result.rowcount != 1:  # type: ignore[attr-defined]
            raise RuntimeError(f"approval {claims.approval_id} was not claimed, or was settled")


class Pauses(Protocol):
    async def paused(self, tenant_id: uuid.UUID, kind: str) -> bool: ...


@dataclass
class SqlPauses:
    """`bravo.watch_pauses`, which the `bravo_watch` lane writes and only a
    person accepting a baseline clears (`dw_sales.adapters.persistence.bravo_watch`)."""

    session_factory: async_sessionmaker[AsyncSession]

    async def paused(self, tenant_id: uuid.UUID, kind: str) -> bool:
        async with tenant_session(
            self.session_factory, TenantScope(tenant_id=tenant_id)
        ) as session:
            found = await session.scalar(
                sa.text("SELECT count(*) FROM bravo.watch_pauses WHERE kind = :kind"),
                {"kind": kind},
            )
        return bool(found)


# Which rule key switches a kind on, by the kind's prefix: DW1's SO writes
# are Sales' (`dw_sales.domain.bravo_writes`). A kind no key covers is off.
SWITCH_KEYS: Final[Mapping[str, str]] = {"so.": "sales_bravo_writes"}
# Which rule names the tenant's Bravo target (ticket 85): the same version
# the switches are read from.
TARGET_KEY: Final = "sales_bravo_writes"
# `platform.rule_versions` is narrowed by tenant only (a version applies to
# the whole tenant): a target read binds no workspace of its own.
_NO_WORKSPACE: Final = WorkspaceId(uuid.UUID(int=0))


@dataclass(frozen=True)
class _Scope:
    tenant_id: TenantId
    workspace_id: WorkspaceId


@dataclass
class SqlSwitches:
    """`Switches` read from the tenant's approved rule version, never cached:
    a kind switched off applies to the next write, and only a version a
    second person decided counts.

    The document's schema is `dw_sales.domain.bravo_writes.BravoWrites`; this
    reads only `kinds.<kind>.enabled` and `uat_proof`, and `target` with its
    `target_uat_proof`, and anything not exactly as that schema writes it
    reads as off, or as no target (`test_gateway_switches.py` holds the two
    together).
    """

    lookup: SqlRuleVersionLookup
    pauses: Pauses

    async def _decided(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, key: str
    ) -> RuleVersion | None:
        """The approved version, when a second person decided it. One its
        proposer applied alone (`applied_directly`, the head's direct path)
        is read as no version, the platform's file: Sales refuses that path
        for this key, and the rule store still accepts it for any key, so
        the write's own door checks it (ticket 85 review)."""
        version = await self.lookup.approved(
            _Scope(TenantId(tenant_id), WorkspaceId(workspace_id)), key
        )
        return None if version is None or version.applied_directly else version

    async def state(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, kind: str) -> SwitchState:
        key = next((k for prefix, k in SWITCH_KEYS.items() if kind.startswith(prefix)), None)
        if key is None:
            return "off"
        # Paused by the change watch (ticket 65) until a person accepts a new
        # baseline; read before the switch, so a paused kind reads paused.
        if await self.pauses.paused(tenant_id, kind):
            return "paused"
        version = await self._decided(tenant_id, workspace_id, key)
        if version is None:
            return "off"  # the platform's file: every kind off
        return "enabled" if switched_on(version.document, kind) else "off"

    async def target(self, tenant_id: uuid.UUID) -> BravoTarget | None:
        version = await self._decided(tenant_id, _NO_WORKSPACE.value, TARGET_KEY)
        if version is None:
            return "uat"  # the platform's file: UAT
        return target_of(version.document)


def target_of(document: Mapping[str, object]) -> BravoTarget | None:
    """UAT unless the version names production with the UAT run that proved
    the gateway there; a version from before the field (1.0.0) is UAT."""
    target = document.get("target", "uat")
    if target == "uat":
        return "uat"
    proof = document.get("target_uat_proof")
    if target == "production" and isinstance(proof, str) and proof.strip():
        return "production"
    return None


def switched_on(document: Mapping[str, object], kind: str) -> bool:
    kinds = document.get("kinds")
    switch = kinds.get(kind) if isinstance(kinds, Mapping) else None
    if not isinstance(switch, Mapping):
        return False
    proof = switch.get("uat_proof")
    return switch.get("enabled") is True and isinstance(proof, str) and bool(proof.strip())
