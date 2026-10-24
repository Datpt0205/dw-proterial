"""Turn an unhandled exception into the 500 inside the CORS layer.

Starlette runs the app's ``Exception`` handler in ``ServerErrorMiddleware``,
the outermost layer, outside ``CORSMiddleware``. A 500 rendered there leaves
without ``Access-Control-Allow-Origin``, so the browser hides it and the web
reports "Mất kết nối mạng" for what was a server error (Sales defect A).

Registered as the innermost middleware, this catches the exception first: the
500 then passes back through request-id and CORS like any other response.
The ``Exception`` handler stays as the last resort for an error raised by a
middleware itself. Both render the same body (``internal_error_response``).
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dw_api.exception_handlers import internal_error_response

_LOG = logging.getLogger(__name__)


class UnexpectedErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self._app(scope, receive, tracking_send)
        except Exception:
            # A response already under way (a stream) cannot be replaced; the
            # outer layer and the server deal with the broken connection.
            if started:
                raise
            # Swallowed here, so logged here: ServerErrorMiddleware re-raises to
            # the server's log, and this layer must not lose that record.
            _LOG.exception("unhandled error on %s %s", scope.get("method"), scope.get("path"))
            response = internal_error_response(Request(scope))
            await response(scope, receive, send)
