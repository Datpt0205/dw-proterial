"""Words reaching a person as a model writes them, and only once checked.

A model's prose is shown only when code can check it (`figure_check`), and a
check that runs after the last word comes too late for a stream: the words are
on the screen. So `released` holds a provider's chunks until a word is whole
and asks the same check of everything written so far, before that word leaves.
What a person saw is always a prefix that passed. A number is never shown cut,
because a chunk boundary inside `1.200` is not a word boundary.

The model answers in the same JSON as an unstreamed call, so a prompt, its
evals and its schema do not change with the transport: `JsonStringField` reads
the one string field out of the JSON as it arrives. The schema itself can only
be validated at the end, so a stream ends in the validated output or an error,
and a caller that already showed words replaces them (`ChatReplace`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dw_agent_runtime.model.gateway import ModelUsage

_LOG = logging.getLogger("dw_agent_runtime.model")
_ESCAPES: Final = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class WordingRefusedError(Exception):
    """A word did not pass the check: the rest of the wording is not shown."""


@dataclass(frozen=True, slots=True)
class StreamedAnswer:
    """How an adapter ends a stream: what it parsed, and the call's usage when
    the provider reported it."""

    parsed: dict[str, object]
    usage: ModelUsage | None = None


class JsonStringField:
    """Reads one top-level string field out of JSON arriving in pieces.

    Everything before the object (a code fence) and every other key or value
    is skipped, a quoted string at a time, so a value holding the field's name
    in its text is not the field. `feed` returns the field's text decoded so
    far; a piece that ends inside an escape holds it for the next piece.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._depth = 0
        self._in_string = False
        self._escaped = False
        self._token: list[str] = []
        self._key_matched = False
        self._after_colon = False
        self._reading = False
        self._done = False
        self._unicode: list[str] = []
        self._high: int | None = None

    def feed(self, piece: str) -> str:
        out: list[str] = []
        for char in piece:
            if self._done:
                break
            if self._reading:
                self._read(char, out)
            elif self._in_string:
                self._skip(char)
            else:
                self._structure(char)
        return "".join(out)

    def _structure(self, char: str) -> None:
        if char == "{":
            self._depth += 1
        elif char == "}":
            self._depth -= 1
        elif char == '"':
            if self._depth == 1 and self._key_matched and self._after_colon:
                self._reading = True
            else:
                self._in_string = True
                self._token = []
        elif char == ":" and self._depth == 1:
            self._after_colon = True
        elif char == "," and self._depth == 1:
            self._key_matched = self._after_colon = False

    def _skip(self, char: str) -> None:
        if self._escaped:
            self._escaped = False
            self._token.append("\\" + char)
        elif char == "\\":
            self._escaped = True
        elif char == '"':
            self._in_string = False
            if self._depth == 1:
                self._key_matched = "".join(self._token) == self._name
        else:
            self._token.append(char)

    def _read(self, char: str, out: list[str]) -> None:
        if self._unicode:
            self._unicode.append(char)
            if len(self._unicode) == 5:
                self._code_unit(int("".join(self._unicode[1:]), 16), out)
                self._unicode = []
        elif self._escaped:
            self._escaped = False
            if char == "u":
                self._unicode = [char]
            else:
                out.append(_ESCAPES.get(char, char))
        elif char == "\\":
            self._escaped = True
        elif char == '"':
            self._reading = False
            self._done = True
        else:
            out.append(char)

    def _code_unit(self, unit: int, out: list[str]) -> None:
        """A `\\uXXXX`, a pair of them for a character past the BMP."""
        if 0xD800 <= unit < 0xDC00:
            self._high = unit
        elif 0xDC00 <= unit < 0xE000 and self._high is not None:
            out.append(chr(0x10000 + (self._high - 0xD800) * 0x400 + (unit - 0xDC00)))
            self._high = None
        else:
            out.append(chr(unit))


async def released(
    pieces: AsyncGenerator[str, None], allowed: Callable[[str], bool]
) -> AsyncGenerator[str, None]:
    """``pieces`` as whole words, each only once ``allowed`` holds for the text
    so far. A word that fails ends the stream with `WordingRefusedError`."""
    shown = ""
    held = ""
    # Closed as soon as a word fails: an unread stream holds the model's one
    # slot until it has written everything nobody will see.
    async with aclosing(pieces) as source:
        async for piece in source:
            held += piece
            cut = max(held.rfind(" "), held.rfind("\n"), held.rfind("\t")) + 1
            if cut == 0:
                continue
            ready, held = held[:cut], held[cut:]
            if not allowed(shown + ready):
                raise WordingRefusedError
            shown += ready
            yield ready
    if held:
        if not allowed(shown + held):
            raise WordingRefusedError
        yield held


# ------------------------------------------------------------ chat events --


class ChatStep(BaseModel):
    """What the worker is doing now, in its own words."""

    model_config = ConfigDict(frozen=True)

    key: str
    title: str


class ChatDelta(BaseModel):
    """More of the answer, checked."""

    model_config = ConfigDict(frozen=True)

    text: str


class ChatReplace(BaseModel):
    """The answer is this instead of what was shown: the wording stopped being
    checkable part way, and code's own sentence takes its place."""

    model_config = ConfigDict(frozen=True)

    text: str


@dataclass(frozen=True, slots=True)
class ChatDone[ViewT: BaseModel]:
    """The stored turn: what a reload of the session shows."""

    view: ViewT


type ChatEvent[ViewT: BaseModel] = ChatStep | ChatDelta | ChatReplace | ChatDone[ViewT]

_NAMES: Final[dict[type[BaseModel], str]] = {
    ChatStep: "step",
    ChatDelta: "delta",
    ChatReplace: "replace",
}
_FAILED: Final = "Không trả lời được lúc này. Hãy hỏi lại."
# `no-store`: a turn is one person's. `X-Accel-Buffering`: a proxy that buffers
# by default (nginx, should a plant put one in front) passes each frame on.
SSE_HEADERS: Final = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
SSE_MEDIA_TYPE: Final = "text/event-stream"


def _encoded(event: ChatEvent[Any]) -> bytes:
    if isinstance(event, ChatDone):
        return _frame("done", event.view.model_dump_json())
    return _frame(_NAMES[type(event)], event.model_dump_json())


def _frame(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode()


async def opened_stream[ViewT: BaseModel](
    events: AsyncGenerator[ChatEvent[ViewT], None],
    record: Callable[[ViewT], Awaitable[ViewT]],
) -> AsyncGenerator[bytes, None]:
    """``events`` as Server-Sent Events, its first event already taken: what
    refuses a request (a scope, another person's session) happens before that
    event, so it is still a status and not a frame in a 200. ``record`` is the
    route's `Idempotency-Key` operation, given the view when the turn is kept."""
    first = await anext(events)
    return _frames(first, events, record)


async def _frames[ViewT: BaseModel](
    first: ChatEvent[ViewT],
    events: AsyncGenerator[ChatEvent[ViewT], None],
    record: Callable[[ViewT], Awaitable[ViewT]],
) -> AsyncGenerator[bytes, None]:
    """The response has started, so a failure can no longer be a status: it is
    one last `error` frame, in fixed words, and the log says what happened by
    kind only."""
    try:
        yield _encoded(first)
        async with aclosing(events) as stream:
            async for event in stream:
                if isinstance(event, ChatDone):
                    await record(event.view)
                yield _encoded(event)
    except Exception as exc:
        _LOG.warning("chat stream failed: %s", type(exc).__name__)
        yield _frame("error", json.dumps({"message": _FAILED}, ensure_ascii=False))
