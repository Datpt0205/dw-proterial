"""DW2 reads an `.eml` file through the reader sandbox's client that exists
(Sales'), adapted at the composition root (ADR 0013 decision 2, the interim):
the answer is DW2's own type, a refusal keeps its reason, and a reader that
does not answer still raises."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from dw_kernel.errors import InfrastructureError
from dw_platform.domain.messages import EmailAddress, InboundMessage
from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_sales.application import mail_drop as sales
from dw_worker.purchasing_reader import PurchasingMailReader

pytestmark = pytest.mark.unit


class SalesReader:
    def __init__(self, answer: sales.MailFile | sales.MailRefused | None) -> None:
        self.answer = answer

    async def read_mail(self, data: bytes) -> sales.MailFile | sales.MailRefused:
        if self.answer is None:
            raise InfrastructureError("the reader gave no answer")
        return self.answer


def _message(data: bytes) -> InboundMessage:
    return InboundMessage(
        message_id="eml-" + hashlib.sha256(data).hexdigest(),
        sender=EmailAddress(address="an@buyer.example"),
        subject="PR",
        received_at=datetime(2026, 11, 2, tzinfo=UTC),
        body_text="",
    )


async def test_a_read_mail_is_dw2_s_own_type_with_every_attachment() -> None:
    message = _message(b"x")
    read = await PurchasingMailReader(
        SalesReader(sales.MailFile(message=message, contents={"a1": b"bytes"}))
    ).read_mail(b"x")
    assert read == MailFile(message=message, contents={"a1": b"bytes"})


async def test_a_refusal_keeps_its_reason() -> None:
    read = await PurchasingMailReader(SalesReader(sales.MailRefused("not a mail"))).read_mail(b"x")
    assert read == MailRefused("not a mail")


async def test_a_reader_that_does_not_answer_still_raises() -> None:
    with pytest.raises(InfrastructureError):
        await PurchasingMailReader(SalesReader(None)).read_mail(b"x")
