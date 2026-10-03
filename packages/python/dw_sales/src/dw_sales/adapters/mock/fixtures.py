"""Where the mock's fixture files live and how they are read.

One place, so the adapters, the attachment generator and the tests agree on
it. Every name, company, domain and number in these files is fictional.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

MOCK_ROOT = Path(__file__).resolve().parent
DATA_DIR = MOCK_ROOT / "data"
ATTACHMENTS_DIR = MOCK_ROOT / "attachments"


def read_records[RecordT: BaseModel](path: Path, model: type[RecordT]) -> tuple[RecordT, ...]:
    """Every record in a JSON array file, each validated by ``model``.

    A record that fails names its position, because these files are edited by
    hand and "1 validation error for Quotation" does not say which of 25.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} must hold a JSON array")
    records: list[RecordT] = []
    for index, entry in enumerate(raw):
        try:
            records.append(model.model_validate(entry))
        except ValidationError as exc:
            raise ValueError(
                f"{path.name}[{index}] is not a valid {model.__name__}: {exc}"
            ) from exc
    return tuple(records)


def attachment_file_name(message_id: str, name: str) -> str:
    """The file a message's attachment called ``name`` is kept in.

    Prefixed with the message id because two messages may carry files with the
    same name and different content (a PO re-sent under its original name).
    """
    return f"{message_id}_{name}"


def attachment_path(attachments_dir: Path, message_id: str, name: str) -> Path:
    return attachments_dir / attachment_file_name(message_id, name)
