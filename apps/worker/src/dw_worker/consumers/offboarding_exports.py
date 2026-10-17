"""Offboarding export bundles, deleted once their term is over.

The offboarding lane writes the departed tenant's whole data set to the export
bucket so it can be handed over, then purges everything else. Nothing deleted
the bundle, so a tenant that left kept a full copy, personal data included, in
object storage for ever (failure-modes #6). `offboarding_exports.retain_days` in
the retention policy is the term (30 days, decided by Đạt 2026-10-18), counted
from the instant the bundle was written, which its key carries
(`export_key_for`).

Driven by the bucket, not by `tenant_offboarding_requests.export_key`: a request
resumed after a dead worker writes a second bundle under a new stamp and the
row then names only the second, so the row cannot see every copy. A key this
lane did not write (`export_written` returns `None`) is kept and counted.

Each deletion is on the audit log of the bundle's own tenant, as this lane
(ADR 0011-a-background-lane-audits-as-itself), in the transaction that deletes
it: no row, no deletion.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from dw_kernel.ports import UtcClock
from dw_worker.consumers.offboarding import BucketPort, export_written

logger = logging.getLogger("dw_worker.offboarding_exports")

# The worker registry name: the lane's actor on the audit log. Renaming it
# changes that actor, so a rename is a decision (ADR 0011).
LANE = "offboarding_exports_retention"


class ExportDeletionAuditPort(Protocol):
    """Structurally `dw_platform`'s `SqlOffboardingExportAudit`: writes the
    deletion's audit row and runs `delete` in the same transaction. `False`
    when the tenant has nothing left to record it against; the bundle is then
    kept."""

    async def delete_audited(
        self,
        tenant_id: UUID,
        export_key: str,
        *,
        occurred_at: datetime,
        details: Mapping[str, object],
        delete: Callable[[], Awaitable[None]],
    ) -> bool: ...


@dataclass(frozen=True)
class OffboardingExportRetention:
    """Implements `RetentionPrunePort` for the export bucket."""

    exports: BucketPort
    audit: ExportDeletionAuditPort
    # `offboarding_exports.retain_days`, validated (1..365, required) where the
    # policy is loaded.
    retain: timedelta
    policy_version: str
    batch_limit: int
    clock: UtcClock

    async def prune(self) -> None:
        now = self.clock.now()
        cutoff = now - self.retain
        deleted = unrecognised = held = 0
        for key in sorted(await self.exports.list_objects("")):
            if deleted + held >= self.batch_limit:
                break
            written = export_written(key)
            if written is None:
                unrecognised += 1
                continue
            tenant_id, written_at = written
            if written_at >= cutoff:
                continue
            if await self.audit.delete_audited(
                tenant_id,
                key,
                occurred_at=now,
                details={
                    "policy_version": self.policy_version,
                    "written_at": written_at.isoformat(),
                },
                delete=_deleting(self.exports, key),
            ):
                deleted += 1
            else:
                held += 1
        if deleted or unrecognised or held:
            logger.info(
                "offboarding export retention pass",
                extra={
                    "deleted": deleted,
                    # Not this lane's shape: kept, and worth a look if it grows.
                    "unrecognised_keys": unrecognised,
                    # Past the term with nothing to audit against: kept.
                    "held_without_audit": held,
                    "policy_version": self.policy_version,
                },
            )


def _deleting(bucket: BucketPort, key: str) -> Callable[[], Awaitable[None]]:
    async def delete() -> None:
        await bucket.delete_object(key)

    return delete
