"""The newest part of a message: what its sender wrote now, without the history.

A reply carries the thread below it, and a forward carries another mail. A
model reading a message (dw_sales ADR 0005) is shown only the newest part, so
a quantity from an older request, or another customer's forwarded words, are
never in front of it; and a span it returns is located in this text, so a
value found only in quoted history is not found at all.

The cut is made from the message's structure, never by asking a model where
the history starts:

- **HTML**, when the message has a text/html part: a ``blockquote`` is
  quoted text wherever it is; the reply containers mail clients write
  (Gmail's ``gmail_quote``, Thunderbird's ``moz-cite-prefix``, Yahoo's
  ``yahoo_quoted``) are skipped whole; Outlook's reply header
  (``divRplyFwdMsg``, ``appendonsend``, ``OutlookMessageHeader``) starts the
  history, and everything after it is cut.
- **Plain text** otherwise: lines quoted with ``>`` are dropped, and the
  text is cut at the first separator a client prints above the history
  (``-----Original Message-----``, ``---------- Forwarded message ---------``,
  an ``On … wrote:`` line, or an Outlook header block ``From:`` followed by
  ``Sent:``/``Date:``).

The text is normalised the way the case stores it: runs of spaces become one,
lines are stripped, and blank lines collapse. Offsets a reading stores (a
body anchor) index into exactly this text, with the subject as its first line.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Final

from dw_sales.domain.messages import InboundMessage

# Elements whose whole content is history, by class or id, as clients write them.
_QUOTE_CLASSES: Final = frozenset({"gmail_quote", "gmail_attr", "moz-cite-prefix", "yahoo_quoted"})
# Where Outlook's history starts: this element and everything after it.
_HISTORY_STARTS: Final = frozenset({"divrplyfwdmsg", "appendonsend", "outlookmessageheader"})
_BLOCKS: Final = frozenset(
    {"p", "div", "br", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
)
_CELLS: Final = frozenset({"td", "th"})
_VOID: Final = frozenset({"br", "hr", "img", "meta", "link", "input", "col", "area", "base", "wbr"})
_SKIPPED: Final = frozenset({"style", "script", "head", "title"})

_SEPARATOR = re.compile(
    r"^\s*-{2,}\s*(?:original message|forwarded message|tin nhắn gốc|thư chuyển tiếp"
    r"|転送メッセージ|元のメッセージ)\s*-{2,}\s*$",
    re.IGNORECASE,
)
_WROTE = re.compile(
    r"^\s*(?:on\s.+\swrote|vào\s.+\sđã viết|.+(?:のメッセージ|が書きました))\s*[:\uff1a]\s*$",
    re.IGNORECASE,
)
# A colon, ASCII or full-width (U+FF1A) as Japanese clients print it.
_HEADER_FROM = re.compile(r"^\s*(?:from|từ|差出人)\s*[:\uff1a]", re.IGNORECASE)
_HEADER_NEXT = re.compile(
    r"^\s*(?:sent|date|gửi|ngày gửi|送信日時|日付)\s*[:\uff1a]", re.IGNORECASE
)
_SPACES = re.compile(r"[ \t\u00a0\u2000-\u200b\u3000]+")


@dataclass(frozen=True, slots=True)
class MessagePart:
    """The subject and the newest body text, normalised; ``cut`` when history
    was removed from below it."""

    subject: str
    body: str
    cut: bool

    @property
    def text(self) -> str:
        """What a reading sees and a body anchor's offsets index into."""
        return f"{self.subject}\n\n{self.body}" if self.body else self.subject

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def newest_part(message: InboundMessage) -> MessagePart:
    """The message's subject and newest body part (module docstring)."""
    if message.body_html is not None and message.body_html.strip():
        body, cut = _from_html(message.body_html)
    else:
        body, cut = _from_plain(message.body_text)
    return MessagePart(subject=_line(message.subject), body=_normalised(body), cut=cut)


def _from_plain(text: str) -> tuple[str, bool]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept: list[str] = []
    cut = False
    for index, line in enumerate(lines):
        if _SEPARATOR.match(line) or _WROTE.match(line) or _outlook_header(lines, index):
            return "\n".join(kept), True
        if line.lstrip().startswith(">"):
            cut = True
            continue
        kept.append(line)
    return "\n".join(kept), cut


def _outlook_header(lines: list[str], index: int) -> bool:
    if not _HEADER_FROM.match(lines[index]):
        return False
    return any(_HEADER_NEXT.match(line) for line in lines[index + 1 : index + 4])


class _Newest(HTMLParser):
    """Collects the text outside quoted history (module docstring)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.cut = False
        self.stopped = False
        # Depth inside a skipped element: >0 means its text is not kept.
        self._skip: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.stopped:
            return
        named = {key: (value or "") for key, value in attrs}
        classes = set(named.get("class", "").split())
        ident = named.get("id", "").lower()
        if ident in _HISTORY_STARTS or (classes & {"OutlookMessageHeader"}):
            self.stopped = self.cut = True
            return
        if self._skip:
            if tag not in _VOID:
                self._skip.append(tag)
            return
        if tag == "blockquote" or classes & _QUOTE_CLASSES:
            self.cut = True
            self._skip.append(tag)
            return
        if tag in _SKIPPED:
            self._skip.append(tag)
            return
        if tag in _BLOCKS:
            self.parts.append("\n")
        elif tag in _CELLS:
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if self.stopped:
            return
        if self._skip:
            if tag in self._skip:
                # Close up to the matching open tag: HTML in mail is rarely
                # balanced, and an unclosed child must not keep the skip open.
                while self._skip and self._skip.pop() != tag:
                    pass
            return
        if tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.stopped and not self._skip:
            self.parts.append(data.replace("\n", " "))


def _from_html(html: str) -> tuple[str, bool]:
    parser = _Newest()
    parser.feed(html)
    parser.close()
    # Block elements open and close lines; the blank lines that leaves
    # between them are markup, not the sender's paragraphs.
    lines = [line for line in "".join(parser.parts).split("\n") if line.strip(" |")]
    return "\n".join(lines), parser.cut


def _line(text: str) -> str:
    return _SPACES.sub(" ", text.replace("\n", " ")).strip()


def _normalised(text: str) -> str:
    lines = [_SPACES.sub(" ", line).strip(" |").strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)
