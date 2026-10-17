"""Offboarding export bundles deleted past their term, against fakes.

The audit half (the row lands in the bundle's tenant, as the lane, in the
deleting transaction) is `dw_platform`'s `test_offboarding.py` against real
Postgres. What is here is the lane's own decision: which keys are past the
term, whose they are, and that nothing is deleted without its audit row.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from dw_worker.consumers.offboarding import export_key_for, export_written
from dw_worker.consumers.offboarding_exports import OffboardingExportRetention

pytestmark = pytest.mark.unit

TENANT = uuid.UUID(int=1)
OTHER_TENANT = uuid.UUID(int=2)
NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
TERM = timedelta(days=30)


@dataclass
class _Bucket:
    objects: dict[str, bytes] = field(default_factory=dict)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = data
        return key

    async def get_object(self, key: str) -> bytes:
        return self.objects[key]

    async def list_objects(self, prefix: str) -> list[str]:
        return [k for k in self.objects if k.startswith(prefix)]

    async def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


@dataclass
class _Audit:
    """Honours `SqlOffboardingExportAudit.delete_audited`: records, then runs
    the deletion; refuses (no record, no deletion) for a tenant with nothing
    to record against."""

    no_workspace: set[uuid.UUID] = field(default_factory=set)
    recorded: list[tuple[uuid.UUID, str, Mapping[str, object]]] = field(default_factory=list)

    async def delete_audited(
        self,
        tenant_id: uuid.UUID,
        export_key: str,
        *,
        occurred_at: datetime,
        details: Mapping[str, object],
        delete: Callable[[], Awaitable[None]],
    ) -> bool:
        if tenant_id in self.no_workspace:
            return False
        self.recorded.append((tenant_id, export_key, details))
        await delete()
        return True


@dataclass(frozen=True)
class _Clock:
    def now(self) -> datetime:
        return NOW


def _lane(bucket: _Bucket, audit: _Audit, batch_limit: int = 1000) -> OffboardingExportRetention:
    return OffboardingExportRetention(
        exports=bucket,
        audit=audit,
        retain=TERM,
        policy_version="1.8.0",
        batch_limit=batch_limit,
        clock=_Clock(),
    )


def _bundle(tenant_id: uuid.UUID, age: timedelta) -> str:
    return export_key_for(tenant_id, NOW - age)


def test_the_key_carries_its_tenant_and_write_time_back() -> None:
    written_at = datetime(2026, 9, 1, 8, 30, 15, tzinfo=UTC)
    assert export_written(export_key_for(TENANT, written_at)) == (TENANT, written_at)


@pytest.mark.parametrize(
    "key",
    [
        "readme.txt",
        f"{TENANT}/offboarding-latest.zip",
        f"{TENANT}/nested/offboarding-20260901T083015Z.zip",
        "not-a-tenant/offboarding-20260901T083015Z.zip",
    ],
)
def test_a_key_this_lane_did_not_write_is_not_read_as_a_bundle(key: str) -> None:
    assert export_written(key) is None


async def test_a_bundle_past_its_term_is_deleted_on_its_own_tenants_audit_log() -> None:
    old = _bundle(TENANT, TERM + timedelta(hours=1))
    bucket, audit = _Bucket({old: b"zip"}), _Audit()

    await _lane(bucket, audit).prune()

    assert old not in bucket.objects
    assert [(t, k) for t, k, _ in audit.recorded] == [(TENANT, old)]
    assert audit.recorded[0][2]["policy_version"] == "1.8.0"


async def test_a_bundle_inside_its_term_is_kept() -> None:
    young = _bundle(TENANT, TERM - timedelta(hours=1))
    bucket, audit = _Bucket({young: b"zip"}), _Audit()

    await _lane(bucket, audit).prune()

    assert young in bucket.objects
    assert audit.recorded == []


async def test_another_tenants_bundle_is_untouched_by_this_ones_expiry() -> None:
    """One tenant's bundle expiring deletes that bundle only: the other
    tenant's younger one stays, and the record goes to the expiring tenant."""
    mine = _bundle(TENANT, TERM + timedelta(days=5))
    theirs = _bundle(OTHER_TENANT, timedelta(days=2))
    bucket, audit = _Bucket({mine: b"a", theirs: b"b"}), _Audit()

    await _lane(bucket, audit).prune()

    assert set(bucket.objects) == {theirs}
    assert {t for t, _, _ in audit.recorded} == {TENANT}


async def test_every_copy_of_a_resumed_request_expires_not_only_the_recorded_one() -> None:
    """A resumed request writes a second bundle; the request row names only
    that one, so the bucket, not the row, says what exists."""
    first = _bundle(TENANT, TERM + timedelta(days=2))
    second = _bundle(TENANT, TERM + timedelta(days=1))
    bucket, audit = _Bucket({first: b"1", second: b"2"}), _Audit()

    await _lane(bucket, audit).prune()

    assert bucket.objects == {}


async def test_no_audit_row_means_no_deletion() -> None:
    old = _bundle(TENANT, TERM + timedelta(days=1))
    bucket, audit = _Bucket({old: b"zip"}), _Audit(no_workspace={TENANT})

    await _lane(bucket, audit).prune()

    assert old in bucket.objects


async def test_an_object_of_another_shape_is_kept_whatever_its_age() -> None:
    bucket, audit = _Bucket({"manual/2020-backup.zip": b"x"}), _Audit()

    await _lane(bucket, audit).prune()

    assert "manual/2020-backup.zip" in bucket.objects


async def test_one_pass_deletes_at_most_the_batch_limit() -> None:
    keys = [_bundle(uuid.UUID(int=10 + i), TERM + timedelta(days=1)) for i in range(3)]
    bucket, audit = _Bucket(dict.fromkeys(keys, b"z")), _Audit()

    await _lane(bucket, audit, batch_limit=2).prune()

    assert len(bucket.objects) == 1
    assert len(audit.recorded) == 2
