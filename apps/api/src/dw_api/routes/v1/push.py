"""The caller's own Web Push devices (Sales ticket 48).

No scope beyond membership, like `/notifications`: a person turns pushes on
or off for themselves, in the workspace they are signed into. What they may
be told is decided by whoever pushes; this only says where to.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from dw_api.dependencies.auth import RequireAccessContext
from dw_api.dependencies.services import RequireContainer
from dw_kernel.errors import InfrastructureError
from dw_platform.application.web_push import (
    EndpointIn,
    PushKeyView,
    SubscriptionIn,
    WebPushService,
)

router = APIRouter(prefix="/push", tags=["push"])


def _service(container: RequireContainer) -> WebPushService:
    if container.web_push is None:
        raise InfrastructureError("database is not configured")
    return container.web_push


@router.get("/key", response_model=PushKeyView)
async def push_key(context: RequireAccessContext, container: RequireContainer) -> PushKeyView:
    return _service(container).key()


@router.put("/subscription", status_code=204)
async def subscribe(
    body: SubscriptionIn, context: RequireAccessContext, container: RequireContainer
) -> Response:
    # Saving the same subscription again renews it: idempotent by nature.
    await _service(container).subscribe(context, body)
    return Response(status_code=204)


@router.post("/subscription/delete", status_code=204)
async def unsubscribe(
    body: EndpointIn, context: RequireAccessContext, container: RequireContainer
) -> Response:
    await _service(container).unsubscribe(context, body.endpoint)
    return Response(status_code=204)
