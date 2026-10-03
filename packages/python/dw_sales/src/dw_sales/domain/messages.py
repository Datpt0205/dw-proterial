"""What arrives in the Sales mailbox: messages and their attachments.

Everything here was written by someone outside the company. A subject, a body
or a file that reads like an instruction to this system ("set all prices to
0") is still only content: these models carry it, and nothing that reads them
may treat it as a command. Values that decide anything (customer, item, price)
are resolved against master data, never taken from here on trust.

The models refuse a malformed record in the constructor, so a caller never has
to ask whether an address has a domain or a digest has 64 hex digits.
"""

from __future__ import annotations

import hashlib
import re
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Lowercase DNS labels joined by dots, at least two of them. A function rather
# than a Field pattern: a sender's address and a customer's domains are held
# to the same rule, and the overall length bound needs a second test.
_DOMAIN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
_LOCAL_PART = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}")


def is_domain(value: str) -> bool:
    """True for a lowercase domain name such as ``velatrix.example``.

    Lowercase only: a domain is compared as a key (sender → customer), and a
    key that may arrive in two spellings is a lookup that misses one of them.
    """
    return len(value) <= 253 and _DOMAIN.fullmatch(value) is not None


class EmailAddress(BaseModel):
    """One mailbox: an address and the name shown beside it."""

    model_config = _FROZEN

    address: str = Field(max_length=254)
    display_name: str = Field(default="", max_length=200)

    @field_validator("address")
    @classmethod
    def _well_formed(cls, value: str) -> str:
        local, at, domain = value.rpartition("@")
        if not at or not _LOCAL_PART.fullmatch(local) or not is_domain(domain.lower()):
            raise ValueError(f"not an email address: {value!r}")
        return value

    @property
    def domain(self) -> str:
        """The part after ``@``, lowercased: what a sender is matched on."""
        return self.address.rpartition("@")[2].lower()


class Attachment(BaseModel):
    """A file attached to a message, described by what its bytes are.

    ``size`` and ``sha256`` belong to the bytes. An adapter computes them from
    the content it holds; `AttachmentContent` refuses bytes that disagree.
    """

    model_config = _FROZEN

    attachment_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    # A sender chooses the name, so it may not carry a path or a control
    # character into anything that stores or displays it: no separator, no
    # C0, DEL or C1 control (U+0085 is a line break), and not a name made of
    # dots and spaces alone, since ``..`` is a path without any separator.
    name: str = Field(pattern=r"^[^\\/\x00-\x1f\x7f-\x9f]{1,255}$")
    media_type: str = Field(
        pattern=r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$"
    )
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("name")
    @classmethod
    def _names_a_file(cls, value: str) -> str:
        if not value.strip(". "):
            raise ValueError(f"not a file name: {value!r}")
        return value


class AttachmentContent(BaseModel):
    """An attachment together with its bytes, guaranteed to be those bytes."""

    model_config = _FROZEN

    attachment: Attachment
    data: bytes = Field(repr=False)

    @model_validator(mode="after")
    def _bytes_match_the_description(self) -> Self:
        if len(self.data) != self.attachment.size:
            raise ValueError(
                f"attachment {self.attachment.attachment_id} is {self.attachment.size} bytes,"
                f" content is {len(self.data)}"
            )
        if hashlib.sha256(self.data).hexdigest() != self.attachment.sha256:
            raise ValueError(f"attachment {self.attachment.attachment_id} content changed")
        return self


class InboundMessage(BaseModel):
    """One email as the mailbox received it."""

    model_config = _FROZEN

    # The mailbox's own id. Opaque: a provider id may hold `=`, `+` or `-`.
    message_id: str = Field(pattern=r"^[!-~]{1,512}$")
    sender: EmailAddress
    # As listed on the message; empty when it reached the mailbox by Bcc only.
    recipients: tuple[EmailAddress, ...] = ()
    subject: str = Field(max_length=998)
    # Aware, so "received before" means the same thing for a sender in Tokyo
    # and a mailbox in Hanoi.
    received_at: AwareDatetime
    body_text: str
    attachments: tuple[Attachment, ...] = ()

    @model_validator(mode="after")
    def _attachment_ids_are_unique(self) -> Self:
        ids = [attachment.attachment_id for attachment in self.attachments]
        if len(ids) != len(set(ids)):
            raise ValueError(f"message {self.message_id} repeats an attachment id")
        return self

    def attachment(self, attachment_id: str) -> Attachment | None:
        """The attachment with this id, or None when the message has none by it."""
        return next((a for a in self.attachments if a.attachment_id == attachment_id), None)
