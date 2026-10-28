"""Request timing: one log line per request, so latency is measured, not guessed.

``request_timing GET /api/v1/sales/orders/{case_id} 200 41.7ms``: the method,
the route's template (never the concrete path, which carries ids), the
status and the wall time inside the API. ``scripts/route_latency.py`` reads
these lines from the container's log and prints p50/p95/p99 per route, on a
test stack or at the customer's, from whatever traffic the log holds
(2026-10-28: the source drawer took 11 s on every open and no number said so).
"""

from __future__ import annotations

import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_LOG = logging.getLogger("dw_api.timing")
# uvicorn configures its own loggers only and the root logger drops INFO, so
# this one writes to stderr itself.
_HANDLER = logging.StreamHandler()
_HANDLER.setFormatter(logging.Formatter("%(message)s"))
_LOG.addHandler(_HANDLER)
_LOG.setLevel(logging.INFO)
_LOG.propagate = False
# A path no route matched (a 404, a probe) is logged with its ids masked.
_ID = re.compile(r"/[0-9a-fA-F-]{8,}|/\d+(?=/|$)")


def route_template(request: Request) -> str:
    """The matched route's template, its mount prefix included; the masked
    path when no route matched.

    FastAPI 0.141 hands an included router's route over with its own path
    (``/sales/orders/{case_id}``), without the prefix it was included under
    (measured 2026-10-28), so the prefix is read off the concrete path: the
    part before the route's own path, filled with this request's values.
    """
    path = request.url.path
    template = getattr(request.scope.get("route"), "path_format", None)
    if isinstance(template, str):
        params = {k: str(v) for k, v in request.scope.get("path_params", {}).items()}
        try:
            concrete = template.format(**params)
        except (KeyError, IndexError, ValueError):
            concrete = ""
        if concrete and path.endswith(concrete):
            return path[: len(path) - len(concrete)] + template
    return _masked(path)


def _masked(path: str) -> str:
    return _ID.sub("/{id}", path)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            _LOG.info(
                "request_timing %s %s %d %.1fms",
                request.method,
                route_template(request),
                status,
                elapsed_ms,
            )
