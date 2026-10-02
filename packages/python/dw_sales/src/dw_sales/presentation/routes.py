"""HTTP surface. Authorization belongs where the mutation is."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from dw_sales.application.handlers import HandleSales
from dw_sales.domain.entities import SalesRequest

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=200)


def build_router(handler: HandleSales) -> APIRouter:
    """Injected, never resolved from a global: the app owns the wiring."""

    @router.post("/requests")
    async def create(body: _Body) -> dict[str, str]:
        # Tenancy comes from the verified access context in a real context, never
        # from the body. Fixed here so the generated slice cannot look like a
        # place where a client supplies its own tenant.
        request = SalesRequest(
            request_id=uuid.uuid4(), tenant_id=uuid.UUID(int=0), subject=body.subject
        )
        return {"summary": await handler(request)}

    return router
