"""Bravo answered offline: procedure results and lookups recorded beforehand.

Until ticket 49 lets DW read Bravo, a procedure's result is the one a trace
recorded (ticket 59: "proc Bravo tạm dùng kết quả ghi trong trace"). A call
that was not recorded, with exactly these parameters, has no answer: it raises
`UndecidableError` rather than return something plausible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from dw_bravo.expression import UndecidableError


def _key_value(value: object) -> object:
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal | int):
        return Decimal(value).normalize()
    if isinstance(value, str | datetime) or value is None:
        return value
    raise TypeError(f"cannot record a parameter of type {type(value).__name__}")


def call_key(
    command: str, parameters: Mapping[str, object]
) -> tuple[str, frozenset[tuple[str, object]]]:
    """A call's identity: the command and its parameters, names case-blind."""
    return command.lower(), frozenset((k.lower(), _key_value(v)) for k, v in parameters.items())


@dataclass
class RecordedProcedures:
    """`ProcedurePort` over recorded results; every call made is kept in `calls`."""

    results: dict[tuple[str, frozenset[tuple[str, object]]], Mapping[str, object]] = field(
        default_factory=dict
    )
    calls: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def record(
        self, command: str, parameters: Mapping[str, object], outputs: Mapping[str, object]
    ) -> None:
        self.results[call_key(command, parameters)] = dict(outputs)

    def call(
        self, command: str, parameters: Mapping[str, object], outputs: Sequence[str]
    ) -> Mapping[str, object]:
        self.calls.append((command, dict(parameters)))
        found = self.results.get(call_key(command, parameters))
        if found is None:
            raise UndecidableError(f"{command}({dict(parameters)}) was not recorded")
        lowered = {k.lower(): v for k, v in found.items()}
        missing = [o for o in outputs if o.lower() not in lowered]
        if missing:
            raise UndecidableError(f"{command}: {', '.join(missing)} not recorded")
        return {o: lowered[o.lower()] for o in outputs}


@dataclass
class RecordedReferences:
    """`ReferencePort` over recorded lookup rows and unique-key answers."""

    rows: dict[tuple[str, object], Mapping[str, object]] = field(default_factory=dict)
    taken: dict[tuple[str, frozenset[tuple[str, object]]], bool] = field(default_factory=dict)

    def find(
        self, lookup_key: str, code: object, filter_key: str | None
    ) -> Mapping[str, object] | None:
        found = self.rows.get((lookup_key.lower(), _key_value(code)))
        if found is None:
            raise UndecidableError(f"lookup {lookup_key} {code!r} was not recorded")
        return found

    def key_taken(
        self, table: str, values: Mapping[str, object], filter_key: str | None, own_id: object
    ) -> bool:
        answer = self.taken.get(call_key(table, values))
        if answer is None:
            raise UndecidableError(f"whether {dict(values)} is taken in {table} was not recorded")
        return answer
