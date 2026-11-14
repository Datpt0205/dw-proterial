"""Migration 7f3def432f82 rewrites each stored reply reading of ticket 32's
shape (one `kind`, its quotes) into thread intents (ticket 26), and back.

Its two statements run here, in Postgres, on a scratch table shaped like the
columns they read (`case_reply`, `order_case_id`) rather than on
`sales.messages`, whose rows need a whole case to exist: what is tested is
the SQL's mapping, and that what it writes is what the application reads
(`CaseReply`).
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_sales.domain.reply_intent import CaseReply

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
_MIGRATION = REPO / "db/migrations/versions/7f3def432f82_sales_sent_messages_thread_intents.py"
_STAMP = {
    "prompt": "sales.reply_intent@1.0.0",
    "model_profile": "onprem",
    "route": "structured_extraction",
    "rules": "sales_order_rules@1.5.2",
}
_QUOTE = {"text": "Please keep the PO as it is.", "start": 10, "end": 38}


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m7f3def432f82", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _old(
    kind: str | None, outcome: str = "read", quotes: list[Any] | None = None
) -> dict[str, Any]:
    reading = {**_STAMP, "outcome": outcome, "kind": kind, "quotes": quotes or []}
    return {"linked_to": "M04", "reading": reading, "picked_by": None}


async def _run(engine: AsyncEngine, statement: str, rows: dict[str, Any]) -> dict[str, Any]:
    table = f"scratch_{uuid.uuid4().hex[:8]}"
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                f"CREATE TEMP TABLE {table} (id text, order_case_id uuid, case_reply jsonb)"
                " ON COMMIT DROP"
            )
        )
        for row_id, (order, reply) in rows.items():
            await conn.execute(
                sa.text(f"INSERT INTO {table} VALUES (:i, :o, CAST(:r AS jsonb))"),
                {"i": row_id, "o": uuid.uuid4() if order else None, "r": json.dumps(reply)},
            )
        await conn.execute(sa.text(statement.replace("sales.messages", table)))
        result = await conn.execute(sa.text(f"SELECT id, case_reply FROM {table}"))
        return {row.id: row.case_reply for row in result}


async def test_each_kind_becomes_the_intent_naming_it_with_its_quotes_and_reads_back(
    migrator: AsyncEngine,
) -> None:
    migration = _migration()
    rows = {
        "accepts": (False, _old("accepts_spec", quotes=[_QUOTE])),
        "keeps": (True, _old("keeps_po_as_is", quotes=[_QUOTE])),
        "counter": (False, _old("counter_proposal", quotes=[_QUOTE])),
        "question": (False, _old("question", quotes=[_QUOTE])),
        "unclear": (False, _old("unclear")),
        "down": (False, _old(None, outcome="unavailable")),
        "unread": (False, {"linked_to": "M04", "reading": None, "picked_by": None}),
    }

    upgraded = await _run(migrator, migration._TO_INTENTS, rows)

    def intents(row: str) -> list[tuple[str, int]]:
        reading = CaseReply.model_validate(upgraded[row]).reading
        assert reading is not None
        return [(i.intent, len(i.quotes)) for i in reading.intents]

    assert intents("accepts") == [("accepts", 1)]
    assert intents("keeps") == [("rejects", 1)]
    assert intents("counter") == [("requests_change", 1)]
    assert intents("question") == [("asks", 1)]
    assert intents("unclear") == [("unclear", 0)]
    assert intents("down") == []
    assert CaseReply.model_validate(upgraded["unread"]).reading is None

    back = await _run(
        migrator,
        migration._TO_KIND,
        {k: (rows[k][0], upgraded[k]) for k in rows},
    )
    assert {k: (v["reading"] or {}).get("kind") for k, v in back.items()} == {
        "accepts": "accepts_spec",
        "keeps": "keeps_po_as_is",
        "counter": "counter_proposal",
        "question": "question",
        "unclear": "unclear",
        "down": None,
        "unread": None,
    }
    assert back["keeps"]["reading"]["quotes"] == [_QUOTE]
