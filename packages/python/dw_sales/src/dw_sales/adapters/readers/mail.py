"""An `.eml` file as DW1's mailbox holds it (ticket 43), read in the sandbox.

The file is the sender's bytes: a Sales PIC's Power Automate flow exports each
mail from outside the company as it arrived, and every header in it below the
receiving server's own was written by whoever sent it. So it is parsed here,
in the reader sandbox, and the answer is an `InboundMessage` whose models
refuse a malformed record, with each attachment's bytes beside it.

- **The message id is the file's sha256** (``eml-<hex>``): the same file is
  the same message, whichever copy of it arrives.
- **When it arrived** is the topmost ``Received:`` stamp, the receiving
  server's; failing that, ``Date:``. A file with neither is refused: the
  mailbox is ordered by arrival, and a time made up here would put a mail
  wherever the guess fell (and give two copies of one file two keys).
- **Who vouches for the sender** is the topmost ``Authentication-Results``,
  the one the receiving server prepends. One written by the sender sits below
  it and is never read. No such header is ``none`` for all three: unverified.
- **An attachment** is a part with ``Content-Disposition: attachment``, or a
  file name and no ``inline``. An inline image (a signature logo) is not one.
  An attached mail (``message/rfc822``) is one attachment, the whole mail,
  and its own parts are not this message's.
- A sender's text is never the reason a file is refused, and no refusal
  quotes it: the reasons are sentences this module wrote.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from typing import Final, get_args

from dw_platform.domain.messages import (
    MAX_REFERENCES,
    Attachment,
    EmailAddress,
    InboundMessage,
    MailAuthentication,
    MailAuthResult,
    is_email_address,
)
from dw_sales.adapters.reader_wire import MailRead

# The largest file the mailbox takes: its base64 must fit the sandbox's
# request (32 MB), and Outlook's own limit on what it sends is 20 MB.
MAX_MAIL_BYTES: Final = 20 * 1024 * 1024
MAX_ATTACHMENTS: Final = 50
MAX_RECIPIENTS: Final = 100

_SUBJECT_MAX: Final = 998
_DISPLAY_NAME_MAX: Final = 200
_FILE_NAME_MAX: Final = 255
_MSG_ID: Final = re.compile(r"<[!-;=?-~]{1,994}>")
_AUTH: Final = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.IGNORECASE)
_RESULTS: Final = frozenset(get_args(MailAuthResult))
_CONTROL: Final = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MEDIA_TYPE: Final = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}"
)


def mail_id(data: bytes) -> str:
    """The mailbox's id for a file: its sha256. The caller computes it again
    from the bytes it sent and refuses an answer that names another."""
    return "eml-" + hashlib.sha256(data).hexdigest()


def read_mail(data: bytes) -> MailRead:
    """The message in ``data`` and its attachments' bytes. ValueError when it
    is over the size limit, names no sender or carries no date."""
    if len(data) > MAX_MAIL_BYTES:
        raise ValueError(f"the mail is over {MAX_MAIL_BYTES // (1024 * 1024)} MB")
    mail = BytesParser(policy=policy.default).parsebytes(data)
    if not isinstance(mail, EmailMessage):  # policy.default always makes one
        raise ValueError("the file is not a mail")
    sender = _sender(mail)
    received_at = _received_at(mail)
    body_text, body_html = _bodies(mail)
    attachments: list[Attachment] = []
    contents: dict[str, str] = {}
    for index, part in enumerate(_attachment_parts(mail), start=1):
        if index > MAX_ATTACHMENTS:
            raise ValueError(f"the mail has more than {MAX_ATTACHMENTS} attachments")
        content = _payload(part)
        attachment = Attachment(
            attachment_id=f"a{index}",
            name=_file_name(part, index),
            media_type=_media_type(part),
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        attachments.append(attachment)
        contents[attachment.attachment_id] = base64.b64encode(content).decode("ascii")
    message = InboundMessage(
        message_id=mail_id(data),
        sender=sender,
        recipients=_recipients(mail),
        subject=_one_line(_header(mail, "Subject"))[:_SUBJECT_MAX],
        received_at=received_at,
        body_text=body_text,
        body_html=body_html,
        attachments=tuple(attachments),
        authentication=_authentication(mail),
        internet_message_id=_message_id(_header(mail, "Message-ID")),
        references=_references(mail),
    )
    return MailRead(message=message, contents=contents)


# ------------------------------------------------------------------ headers --


def _header(mail: Message, name: str) -> str:
    """A header's text, or "" where it is absent or will not parse: a header
    that breaks the parser is a header this mail does not have."""
    try:
        value = mail.get(name)
    except Exception:
        return ""
    return "" if value is None else str(value)


def _one_line(value: str) -> str:
    return " ".join(_CONTROL.sub(" ", value).split())


def _address(name: str, address: str) -> EmailAddress | None:
    if not is_email_address(address):
        return None
    return EmailAddress(address=address, display_name=_one_line(name)[:_DISPLAY_NAME_MAX])


def _sender(mail: Message) -> EmailAddress:
    for name, address in getaddresses([_header(mail, "From")]):
        found = _address(name, address)
        if found is not None:
            return found
    raise ValueError("the mail names no sender")


def _recipients(mail: Message) -> tuple[EmailAddress, ...]:
    listed = getaddresses([_header(mail, "To"), _header(mail, "Cc")])
    found = [a for a in (_address(name, address) for name, address in listed) if a is not None]
    return tuple(found[:MAX_RECIPIENTS])


def _date(value: str) -> datetime | None:
    try:
        when = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError):
        return None
    # `-0000` is "the zone is not known" (RFC 5322): read as UTC.
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def _received_at(mail: Message) -> datetime:
    stamps = mail.get_all("Received") or []
    if stamps:
        # The date follows the last ";" of a Received header (RFC 5321).
        when = _date(str(stamps[0]).rpartition(";")[2])
        if when is not None:
            return when
    when = _date(_header(mail, "Date"))
    if when is None:
        raise ValueError("the mail carries no date it was received or sent")
    return when


def _authentication(mail: Message) -> MailAuthentication:
    results = mail.get_all("Authentication-Results") or []
    if not results:
        return MailAuthentication()
    found: dict[str, str] = {}
    for method, result in _AUTH.findall(str(results[0])):
        found.setdefault(method.lower(), result.lower())
    return MailAuthentication.model_validate(
        {method: result for method, result in found.items() if result in _RESULTS}
    )


def _message_id(value: str) -> str | None:
    found = _MSG_ID.search(value)
    return None if found is None else found.group(0)


def _references(mail: Message) -> tuple[str, ...]:
    """In-Reply-To, then References from the newest: nearest ancestor first."""
    ids = _MSG_ID.findall(_header(mail, "In-Reply-To"))
    ids += reversed(_MSG_ID.findall(_header(mail, "References")))
    return tuple(dict.fromkeys(ids))[:MAX_REFERENCES]


# ------------------------------------------------------------------- bodies --


class _Text(HTMLParser):
    """The text of an HTML body, a line per block, scripts and styles left out."""

    _BREAKS: Final = frozenset({"br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"})
    _SKIPPED: Final = frozenset({"script", "style", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIPPED:
            self._skipping += 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED and self._skipping:
            self._skipping -= 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def _decoded(part: Message) -> str:
    """A text part's content; an unknown charset is read as UTF-8 with
    replacement rather than refusing the mail."""
    try:
        content = part.get_content()  # type: ignore[attr-defined]
    except (LookupError, ValueError, AssertionError):
        raw = part.get_payload(decode=True)
        content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
    return content if isinstance(content, str) else ""


def _bodies(mail: EmailMessage) -> tuple[str, str | None]:
    plain = mail.get_body(preferencelist=("plain",))
    html = mail.get_body(preferencelist=("html",))
    body_html = None if html is None else _decoded(html)
    if plain is not None:
        return _decoded(plain), body_html
    if body_html is not None:
        reader = _Text()
        reader.feed(body_html)
        reader.close()
        return reader.text(), body_html
    return "", None


# -------------------------------------------------------------- attachments --


def _attachment_parts(mail: Message) -> Iterator[Message]:
    """Every attachment, depth first. The mail itself is never one."""
    if mail.is_multipart():
        for child in mail.get_payload():
            if isinstance(child, Message):
                yield from _attachments_in(child)


def _attachments_in(part: Message) -> Iterator[Message]:
    disposition = part.get_content_disposition()
    if part.get_content_type() == "message/rfc822":
        # The attached mail whole; its own parts are not this message's.
        if disposition != "inline" or part.get_filename():
            yield part
        return
    if part.is_multipart():
        yield from _attachment_parts(part)
        return
    if disposition == "attachment" or (part.get_filename() and disposition != "inline"):
        yield part


def _payload(part: Message) -> bytes:
    if part.get_content_type() == "message/rfc822":
        inner = part.get_payload()
        mail = inner[0] if isinstance(inner, list) and inner else None
        return mail.as_bytes(policy=policy.SMTP) if isinstance(mail, Message) else b""
    raw = part.get_payload(decode=True)
    return raw if isinstance(raw, bytes) else b""


def _file_name(part: Message, index: int) -> str:
    try:
        name = part.get_filename() or ""
    except Exception:
        name = ""
    # A sender's name for the file: never a path, never a control character.
    name = _CONTROL.sub("", name.replace("\\", "/").rpartition("/")[2]).strip()
    if not name.strip(". "):
        suffix = ".eml" if part.get_content_type() == "message/rfc822" else ""
        return f"tep-dinh-kem-{index}{suffix}"
    if len(name) > _FILE_NAME_MAX:
        stem, dot, extension = name.rpartition(".")
        keep = _FILE_NAME_MAX - len(dot + extension)
        name = (stem[:keep] + dot + extension) if dot and keep > 0 else name[:_FILE_NAME_MAX]
    return name


def _media_type(part: Message) -> str:
    media_type = part.get_content_type().lower()
    return media_type if _MEDIA_TYPE.fullmatch(media_type) else "application/octet-stream"
