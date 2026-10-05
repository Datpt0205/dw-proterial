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

    A record that fails names its position and the fields that failed, because
    these files are edited by hand and "1 validation error for Quotation" does
    not say which of 25. It never names a value: these files stand in for a
    customer's data, and a refusal ends up in a log (spec decision 8).
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path.name} must hold a JSON array")
    records: list[RecordT] = []
    for index, entry in enumerate(raw):
        try:
            records.append(model.model_validate(entry))
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(str(part) for part in error['loc']) or 'record'}: {error['msg']}"
                for error in exc.errors(include_url=False, include_input=False)
            )
            # `from None`: the chained error's own text would carry the input.
            raise ValueError(
                f"{path.name}[{index}] is not a valid {model.__name__}: {problems}"
            ) from None
    return tuple(records)


def attachment_file_name(message_id: str, name: str) -> str:
    """The file a message's attachment called ``name`` is kept in.

    Prefixed with the message id because two messages may carry files with the
    same name and different content (a PO re-sent under its original name).
    """
    return f"{message_id}_{name}"


def attachment_path(attachments_dir: Path, message_id: str, name: str) -> Path:
    return attachments_dir / attachment_file_name(message_id, name)
