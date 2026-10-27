"""An `.eml` file read as the mailbox holds it (ticket 43), in process.

Each file here is built the way Exchange Online hands one to the export a Sales
PIC's flow makes: the receiving server's `Received:` and
`Authentication-Results:` on top, the sender's own headers below them.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime
from email.message import EmailMessage
from email.policy import SMTP

import pytest

from dw_sales.adapters.reader_client import ClientMailReader
from dw_sales.adapters.reader_wire import MailRead, ReaderOp, ReaderReply, ReaderRequest
from dw_sales.adapters.readers.mail import MAX_ATTACHMENTS, read_mail
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.mail_drop import MailFile, MailRefused

_RECEIVED = (
    "from mail-ej1.google.com (209.85.218.48) by SG1PEPF00001.mail.protection.outlook.com"
    " with Microsoft SMTP Server; Mon, 27 Oct 2026 03:28:18 +0000"
)
_AUTH_TOP = (
    "spf=pass (sender IP is 209.85.218.48) smtp.mailfrom=gmail.com; dkim=pass (signature"
    " was verified) header.d=gmail.com;dmarc=pass action=none header.from=gmail.com;"
    "compauth=pass reason=100"
)
_XLSX = b"PK\x03\x04 fictional workbook"


def _mail(
    *,
    received: str | None = _RECEIVED,
    auth: str | None = _AUTH_TOP,
    date: str | None = "Mon, 27 Oct 2026 10:28:00 +0700",
    sender: str = "Khách Hàng <buyer@velatrix.example>",
) -> EmailMessage:
    mail = EmailMessage()
    if received is not None:
        mail["Received"] = received
    if auth is not None:
        mail["Authentication-Results"] = auth
    # Below the server's own: written by whoever sent it, and claiming a pass.
    mail["Authentication-Results"] = "spf=pass; dkim=pass; dmarc=pass"
    mail["From"] = sender
    mail["To"] = "Sales PIC <pic@proterial.example>, not an address"
    mail["Cc"] = "head@proterial.example"
    mail["Subject"] = "Đơn đặt hàng PO 4500012345 — giao tháng 11"
    if date is not None:
        mail["Date"] = date
    mail["Message-ID"] = "<CAF1234@mail.gmail.com>"
    mail["In-Reply-To"] = "<parent@proterial.example>"
    mail["References"] = "<root@velatrix.example> <parent@proterial.example>"
    mail.set_content("Kính gửi Proterial,\nXin gửi PO đính kèm.")
    mail.add_alternative("<p>Kính gửi Proterial,</p><p>Xin gửi <b>PO</b> đính kèm.</p>", "html")
    return mail


def _with_files(mail: EmailMessage) -> EmailMessage:
    mail.add_attachment(
        _XLSX,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="Đơn hàng tháng 11.xlsx",
    )
    # A signature logo: inline, with a Content-ID. Not an attachment.
    mail.add_attachment(
        b"\x89PNG logo", maintype="image", subtype="png", filename="logo.png", disposition="inline"
    )
    forwarded = EmailMessage()
    forwarded["From"] = "old@velatrix.example"
    forwarded["Subject"] = "PO cũ"
    forwarded.set_content("thư cũ")
    forwarded.add_attachment(b"%PDF old", maintype="application", subtype="pdf", filename="cu.pdf")
    mail.add_attachment(forwarded)
    return mail


def _bytes(mail: EmailMessage) -> bytes:
    return mail.as_bytes(policy=SMTP)


def test_a_mail_is_read_with_what_dw1_needs() -> None:
    data = _bytes(_with_files(_mail()))
    message = read_mail(data).message

    assert message.message_id == "eml-" + hashlib.sha256(data).hexdigest()
    assert message.sender.address == "buyer@velatrix.example"
    assert message.sender.display_name == "Khách Hàng"
    assert [r.address for r in message.recipients] == [
        "pic@proterial.example",
        "head@proterial.example",
    ]
    assert message.subject == "Đơn đặt hàng PO 4500012345 — giao tháng 11"
    assert message.received_at == datetime(2026, 10, 27, 3, 28, 18, tzinfo=UTC)
    assert "Xin gửi PO đính kèm." in message.body_text
    assert message.body_html is not None and "<b>PO</b>" in message.body_html
    assert message.internet_message_id == "<CAF1234@mail.gmail.com>"
    # Nearest ancestor first.
    assert message.references == ("<parent@proterial.example>", "<root@velatrix.example>")


def test_attachments_are_the_files_not_the_signature_logo() -> None:
    read = read_mail(_bytes(_with_files(_mail())))
    attachments = read.message.attachments

    assert [(a.attachment_id, a.name, a.media_type) for a in attachments] == [
        (
            "a1",
            "Đơn hàng tháng 11.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("a2", "tep-dinh-kem-2.eml", "message/rfc822"),
    ]
    assert base64.b64decode(read.contents["a1"]) == _XLSX
    assert attachments[0].sha256 == hashlib.sha256(_XLSX).hexdigest()
    # The attached mail is one file: its own PDF is not this message's.
    assert b'filename="cu.pdf"' in base64.b64decode(read.contents["a2"])


def test_only_the_receiving_servers_authentication_counts() -> None:
    verified = read_mail(_bytes(_mail())).message.authentication
    assert (verified.spf, verified.dkim, verified.dmarc) == ("pass", "pass", "pass")

    # The server found the sender out; the "pass" the sender wrote below its
    # header is never read.
    failed = "spf=fail smtp.mailfrom=velatrix.example; dkim=none; dmarc=fail action=quarantine"
    forged = read_mail(_bytes(_mail(auth=failed))).message.authentication
    assert (forged.spf, forged.dkim, forged.dmarc) == ("fail", "none", "fail")
    assert not forged.verified


def test_the_arrival_is_the_servers_stamp_else_the_date() -> None:
    assert read_mail(_bytes(_mail(received=None))).message.received_at == datetime(
        2026, 10, 27, 3, 28, tzinfo=UTC
    )
    with pytest.raises(ValueError, match="no date"):
        read_mail(_bytes(_mail(received=None, date=None)))


def test_a_mail_without_a_sender_is_refused() -> None:
    with pytest.raises(ValueError, match="no sender"):
        read_mail(_bytes(_mail(sender="undisclosed")))


def test_an_html_only_body_gives_a_text_body_too() -> None:
    mail = EmailMessage()
    mail["Received"] = _RECEIVED
    mail["From"] = "buyer@velatrix.example"
    mail["Subject"] = "RFQ"
    mail.set_content(
        "<html><head><style>p{}</style></head><body><p>Xin báo giá</p>"
        "<div>3 mã hàng</div><script>x()</script></body></html>",
        subtype="html",
    )
    message = read_mail(_bytes(mail)).message
    assert message.body_text == "Xin báo giá\n3 mã hàng"


def test_a_file_name_never_carries_a_path() -> None:
    mail = _mail()
    mail.add_attachment(
        b"x", maintype="application", subtype="pdf", filename="..\\..\\etc/passwd\x07.pdf"
    )
    (attachment,) = read_mail(_bytes(mail)).message.attachments
    assert attachment.name == "passwd.pdf"


def test_too_many_attachments_is_a_refusal() -> None:
    mail = _mail()
    for index in range(MAX_ATTACHMENTS + 1):
        mail.add_attachment(b"x", maintype="text", subtype="plain", filename=f"{index}.txt")
    with pytest.raises(ValueError, match="more than"):
        read_mail(_bytes(mail))


def test_the_client_reads_through_the_wire() -> None:
    data = _bytes(_with_files(_mail()))
    read = asyncio.run(ClientMailReader(InProcessReaderTransport()).read_mail(data))
    assert isinstance(read, MailFile)
    assert read.contents["a1"] == _XLSX


def test_the_client_says_why_a_file_was_refused() -> None:
    read = asyncio.run(ClientMailReader(InProcessReaderTransport()).read_mail(b"not a mail"))
    assert isinstance(read, MailRefused)
    assert read.reason == "the mail names no sender"


class _Liar:
    """A reader whose answer belongs to another file."""

    def __init__(self, answer: MailRead) -> None:
        self.answer = answer

    async def call(self, request: ReaderRequest) -> ReaderReply:
        return ReaderReply.answered(ReaderOp.MAIL_READ, self.answer)


def test_the_client_refuses_an_answer_about_another_file() -> None:
    other = read_mail(_bytes(_mail()))
    read = asyncio.run(ClientMailReader(_Liar(other)).read_mail(_bytes(_with_files(_mail()))))
    assert read == MailRefused("the reader's answer names another file than the one sent")


def test_the_client_refuses_bytes_that_are_not_the_attachment() -> None:
    data = _bytes(_with_files(_mail()))
    honest = read_mail(data)
    swapped = MailRead(
        message=honest.message,
        contents={**honest.contents, "a1": base64.b64encode(b"other bytes").decode()},
    )
    read = asyncio.run(ClientMailReader(_Liar(swapped)).read_mail(data))
    assert isinstance(read, MailRefused)
