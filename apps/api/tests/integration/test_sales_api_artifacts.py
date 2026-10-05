"""Downloads are gated per kind on the case's state (ticket 06's table, landed
with the route in 05): before its state 409, as the viewer 403, another
case's artifact 404. Rendering the files is ticket 06's; the records here
are written straight to the store."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sales_api_harness import AN, DIEU, HA, Api, user_id
from sales_flow import order_of, prepared, process, quote

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.artifacts_service import ORDER_GATES, QUOTE_GATES
from dw_sales.application.case_store import ArtifactRecord
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind

pytestmark = pytest.mark.integration

ALPHA = SalesScope(
    TenantId(sid("tenant", "tenant-alpha")), WorkspaceId(sid("workspace", "tenant-alpha:main"))
)


async def _artifact(api: Api, kind: str, case_kind: CaseKind, case: dict[str, Any]) -> str:
    record = ArtifactRecord(
        artifact_id=uuid.uuid4(),
        case_kind=case_kind,
        case_id=uuid.UUID(case["case_id"]),
        case_version=case["case_version"],
        kind=kind,
        template_ref="sales_test@1.0.0",
        sha256="a" * 64,
        content_type="application/octet-stream",
        size_bytes=4,
        created_by=user_id(AN),
        created_at=datetime.now(UTC),
    )
    uow = SqlSalesUnitOfWorkFactory(api.sessions, audit=SqlAuditRepository)
    async with uow(ALPHA) as work:
        await work.artifacts.add(record)
        await work.commit()
    api.artifacts.objects[record.object_key(ALPHA)] = b"file"
    return str(record.artifact_id)


@pytest.mark.parametrize("kind", sorted(ORDER_GATES))
async def test_an_order_artifact_before_its_state_is_refused(api: Api, kind: str) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M01")  # in review: no artifact's state yet
    artifact = await _artifact(api, kind, CaseKind.ORDER, case)

    response = await an.get(f"/orders/{case['case_id']}/artifacts/{artifact}")

    assert response.status_code == 409
    assert response.json()["details"]["kind"] == kind


@pytest.mark.parametrize("kind", sorted(QUOTE_GATES))
async def test_a_quote_artifact_before_its_state_is_refused(api: Api, kind: str) -> None:
    dieu = api.as_(DIEU)
    opened = await process(dieu, "M10")  # received: no artifact's state yet
    case = await quote(dieu, opened["case_id"])
    artifact = await _artifact(api, kind, CaseKind.QUOTE, case)

    response = await dieu.get(f"/quotes/{case['case_id']}/artifacts/{artifact}")

    assert response.status_code == 409


async def test_the_upload_file_is_served_once_prepared_and_never_to_the_viewer(
    api: Api,
) -> None:
    an = api.as_(AN)
    ready = await prepared(an, await order_of(an, "M01"))
    artifact = await _artifact(api, "bravo_upload", CaseKind.ORDER, ready)

    served = await an.get(f"/orders/{ready['case_id']}/artifacts/{artifact}")
    as_viewer = await api.as_(HA).get(f"/orders/{ready['case_id']}/artifacts/{artifact}")

    assert served.status_code == 200 and served.content == b"file"
    assert (
        served.headers["content-disposition"]
        == f'attachment; filename="bravo_upload-{ready["case_id"]}"'
    )
    assert as_viewer.status_code == 403


async def test_another_cases_artifact_is_not_found(api: Api) -> None:
    an = api.as_(AN)
    first = await prepared(an, await order_of(an, "M01"))
    second = await order_of(an, "M06")
    artifact = await _artifact(api, "bravo_upload", CaseKind.ORDER, first)

    response = await an.get(f"/orders/{second['case_id']}/artifacts/{artifact}")

    assert response.status_code == 404
