"""`/api/v1/sales/.../activity`: what DW1's model steps did (slice 3).

Read-only, over `ActivityService`, which decides who may read and what a
response carries (`dw_sales.application.activity`): one case's entries with
`sales.case.read`, a price left out for a caller without `sales.price.read`;
the summary with `sales.overview.read` or `sales.rules.propose`. Every route
depends on the verified access context first, as the Sales router's do; none
takes a support context (fail closed until a support case needs them). With
no data source configured, each answers 503 as the Sales router does.
"""

# No `from __future__ import annotations`: FastAPI resolves the aliases built
# inside `build_activity_router` against the module's globals otherwise.

import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from dw_kernel.errors import InfrastructureError
from dw_platform.application.access_context import AccessContext
from dw_sales.application.activity import ActivityService, ActivitySummaryView, CaseActivityView
from dw_sales.domain.dispositions import CaseKind
from dw_sales.presentation.routes import NOT_CONFIGURED


def build_activity_router(
    activity: ActivityService | None, *, access_context: Callable[..., Any]
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/sales", tags=["sales"])

    def _activity(
        context: Annotated[AccessContext, Depends(access_context)],
    ) -> ActivityService:
        # After the access context, so an unauthenticated caller learns nothing.
        if activity is None:
            raise InfrastructureError(NOT_CONFIGURED, details={"context": "sales"})
        return activity

    Ctx = Annotated[AccessContext, Depends(access_context)]  # noqa: N806 (a type alias)
    Svc = Annotated[ActivityService, Depends(_activity)]  # noqa: N806 (a type alias)

    @router.get("/orders/{case_id}/activity", response_model=CaseActivityView)
    async def order_activity(case_id: uuid.UUID, context: Ctx, svc: Svc) -> CaseActivityView:
        return await svc.case_activity(context, CaseKind.ORDER, case_id)

    @router.get("/quotes/{case_id}/activity", response_model=CaseActivityView)
    async def quote_activity(case_id: uuid.UUID, context: Ctx, svc: Svc) -> CaseActivityView:
        return await svc.case_activity(context, CaseKind.QUOTE, case_id)

    @router.get("/activity", response_model=ActivitySummaryView)
    async def activity_summary(
        context: Ctx,
        svc: Svc,
        start: Annotated[date | None, Query(alias="from")] = None,
        end: Annotated[date | None, Query(alias="to")] = None,
        lane: CaseKind | None = None,
    ) -> ActivitySummaryView:
        return await svc.summary(context, start=start, end=end, lane=lane)

    return router
