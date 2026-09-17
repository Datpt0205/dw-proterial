"""What may be attached, and which parser handles it.

One module so the answer to "is this file accepted?" is the same at the upload
edge and in the worker. Routing is by extension: the browser's content type is
unverified and would decide which paid API receives the bytes.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath

import yaml
from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import DomainError


class AttachmentKind(StrEnum):
    PLAINTEXT = "plaintext"
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"


class AttachmentPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: str
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")

    plaintext_extensions: tuple[str, ...]
    document_extensions: tuple[str, ...]
    image_extensions: tuple[str, ...]
    audio_extensions: tuple[str, ...]

    document_instruction: str = Field(min_length=1)
    image_instruction: str = Field(min_length=1)
    empty_marker: str = Field(min_length=1)

    transcription_model: str = Field(min_length=1)
    transcription_language: str = Field(min_length=1)

    def kind_of(self, filename: str) -> AttachmentKind | None:
        """The parser route, or None when the file is not accepted."""
        suffix = PurePosixPath(filename).suffix.lower()
        for kind, extensions in (
            (AttachmentKind.PLAINTEXT, self.plaintext_extensions),
            (AttachmentKind.DOCUMENT, self.document_extensions),
            (AttachmentKind.IMAGE, self.image_extensions),
            (AttachmentKind.AUDIO, self.audio_extensions),
        ):
            if suffix in extensions:
                return kind
        return None

    def accepted_extensions(self) -> tuple[str, ...]:
        return (
            *self.plaintext_extensions,
            *self.document_extensions,
            *self.image_extensions,
            *self.audio_extensions,
        )

    def require_accepted(self, filename: str) -> AttachmentKind:
        kind = self.kind_of(filename)
        if kind is None:
            raise DomainError(
                "file type is not accepted",
                details={
                    "filename": filename,
                    "accepted": sorted(self.accepted_extensions()),
                },
            )
        return kind


def load_attachment_policy(path: Path) -> AttachmentPolicy:
    return AttachmentPolicy.model_validate(yaml.safe_load(path.read_bytes()))
