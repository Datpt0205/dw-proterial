"""Inbound messages: what their constructors refuse."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from dw_sales.domain.messages import (
    Attachment,
    AttachmentContent,
    EmailAddress,
    InboundMessage,
    MailAuthentication,
    is_email_address,
)

pytestmark = pytest.mark.unit

_DATA = b"PO VLX-PO-2609-0118"


def _attachment(**overrides: Any) -> dict[str, Any]:
    return {
        "attachment_id": "M01-A1",
        "name": "VLX-PO-2609-0118.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size": len(_DATA),
        "sha256": hashlib.sha256(_DATA).hexdigest(),
    } | overrides


def _message(**overrides: Any) -> dict[str, Any]:
    return {
        "message_id": "M01",
        "sender": {"address": "an.trinh@velatrix.example"},
        "recipients": [{"address": "sales@seller.example"}],
        "subject": "PO VLX-PO-2609-0118",
        "received_at": datetime(2026, 9, 21, 1, 12, tzinfo=UTC),
        "body_text": "",
        "attachments": [_attachment()],
    } | overrides


def test_a_sender_is_matched_on_its_lowercased_domain() -> None:
    assert EmailAddress(address="An.Trinh@Velatrix.Example").domain == "velatrix.example"


@pytest.mark.parametrize(
    "address",
    [
        "purchasing@",
        "@velatrix.example",
        "purchasing",
        "a@b",
        "a@b@velatrix.example",
        "a b@x.example",
    ],
)
def test_an_address_without_a_usable_domain_is_refused(address: str) -> None:
    with pytest.raises(ValidationError):
        EmailAddress(address=address)


def test_a_message_without_a_timezone_is_refused() -> None:
    """Without one, "received before" means different things in Tokyo and Hanoi."""
    with pytest.raises(ValidationError):
        InboundMessage.model_validate(_message(received_at=datetime(2026, 9, 21, 8, 12)))


@pytest.mark.parametrize(
    "name",
    ["../PO.xlsx", "..\\PO.xlsx", "..", ".", " ", "PO\x00.xlsx", "PO\x7f.xlsx", "PO\x85.xlsx", ""],
)
def test_an_attachment_name_cannot_carry_a_path_or_a_control_character(name: str) -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(_attachment(name=name))


@pytest.mark.parametrize(
    "name", ["VLX-PO-2609-0118.xlsx", ".PO.xlsx", "注文書 KMH-2026-0925-A.xlsx"]
)
def test_an_ordinary_file_name_is_kept_as_sent(name: str) -> None:
    assert Attachment.model_validate(_attachment(name=name)).name == name


@pytest.mark.parametrize(
    "overrides",
    [{"sha256": "ABC"}, {"size": -1}, {"media_type": "spreadsheet"}, {"attachment_id": "M01 A1"}],
)
def test_an_attachment_description_with_an_impossible_value_is_refused(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        Attachment.model_validate(_attachment(**overrides))


def test_attachment_content_is_exactly_the_bytes_described() -> None:
    attachment = Attachment.model_validate(_attachment())

    assert AttachmentContent(attachment=attachment, data=_DATA).data == _DATA
    with pytest.raises(ValidationError, match="size is not the content's"):
        AttachmentContent(attachment=attachment, data=_DATA + b"!")
    same_size_other_bytes = _DATA.replace(b"0118", b"0119")
    with pytest.raises(ValidationError, match="content changed"):
        AttachmentContent(attachment=attachment, data=same_size_other_bytes)


def test_attachment_ids_repeat_nowhere_in_one_message() -> None:
    with pytest.raises(ValidationError, match="repeats an attachment id"):
        InboundMessage.model_validate(_message(attachments=[_attachment(), _attachment()]))


def test_an_attachment_is_found_by_its_id_within_its_message() -> None:
    message = InboundMessage.model_validate(_message())

    found = message.attachment("M01-A1")
    assert found is not None
    assert found.name == "VLX-PO-2609-0118.xlsx"
    assert message.attachment("M01-A2") is None


@pytest.mark.parametrize(
    ("model", "record", "secret"),
    [
        (EmailAddress, {"address": "secret person@evil.example"}, "secret person"),
        (Attachment, _attachment(name="secret/../PO.xlsx"), "secret"),
    ],
    ids=["address", "file_name"],
)
def test_a_refusal_names_the_field_never_the_value(
    model: type[EmailAddress] | type[Attachment], record: dict[str, Any], secret: str
) -> None:
    """Spec decision 8: an address or a file name is a customer's data in a log."""
    with pytest.raises(ValidationError) as refused:
        model.model_validate(record)

    assert secret not in str(refused.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("an.nguyen@alpha.local", True),
        ("An.Trinh@Velatrix.Example", True),
        ("an.nguyen@", False),
        ("an nguyen@alpha.local", False),
        ("a@b", False),
    ],
)
def test_one_rule_says_what_an_email_address_is(value: str, expected: bool) -> None:
    assert is_email_address(value) is expected
    assert (EmailAddress.model_validate({"address": value}) is not None) if expected else True


def test_a_message_whose_mail_results_are_unknown_reads_as_unverified() -> None:
    """The default proves nothing: ``none`` on all three, never ``pass``."""
    message = InboundMessage.model_validate(_message())

    assert message.authentication == MailAuthentication(spf="none", dkim="none", dmarc="none")


def test_the_mail_systems_results_are_carried_as_stated() -> None:
    results = {"spf": "softfail", "dkim": "fail", "dmarc": "fail"}
    message = InboundMessage.model_validate(_message(authentication=results))

    assert message.authentication.model_dump() == results


@pytest.mark.parametrize("field", ["spf", "dkim", "dmarc"])
def test_a_mail_result_outside_rfc_8601_is_refused(field: str) -> None:
    with pytest.raises(ValidationError):
        MailAuthentication.model_validate({field: "ok"})
