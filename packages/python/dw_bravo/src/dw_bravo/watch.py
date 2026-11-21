# ruff: noqa: E501 - the docstring table is ticket 65's, row for row
"""What a change in Bravo does to DW's writes (ADR 0027 decision 4, ticket 65).

Bravo's vendor and Proterial's admins change Bravo without telling DW. The
gateway measures what DW's writes depend on (a `Fingerprint`); this module
compares two of them and decides, by ticket 65's table, which write kinds go
on, which pause, and what a person is told. It decides only: reading Bravo
is the gateway's, storing and notifying the worker lane's.

| Change | Reaction |
|---|---|
| A layout changed; every rule still parses and the replay of recorded saves agrees | writes go on, with a notice |
| A layout holds a rule the runner cannot evaluate | that screen's writes pause |
| A layout changed and its replay has not agreed (not run, or differs) | that screen's writes pause until it does |
| A column, a trigger, a routine DW calls, the context parser | the dependent write kinds pause |
| An import template | the kinds that create on that screen pause |
| The client version | notice; every kind pauses until the replay passes |
| UAT differs from production | early warning, nothing pauses |
| Bravo could not be read | "could not check since"; past the age limit, every kind pauses |

A pause holds until a person accepts the new baseline (`bravo.watch.accept`,
checked where it is written); nothing here resumes anything.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Literal

from dw_bravo.contract import WRITE_KINDS, WriteKind

ComponentKind = Literal[
    "layout",
    "template",
    "command",
    "columns",
    "trigger",
    "routine",
    "context_parser",
    "client_version",
]
Replay = Literal["agrees", "explained", "differs", "not_run"]

# Past this, a fingerprint DW could not refresh is too old to write under.
MAX_AGE: Final = timedelta(hours=2)


@dataclass(frozen=True)
class Component:
    """One thing a write depends on, as the gateway measured it.

    `name` is the screen for a layout, command or template, the table for
    columns, the trigger's or routine's name otherwise. `table` is a
    trigger's table; `screens` the screens whose layout calls a routine
    (empty: every write depends on it, e.g. the permission functions);
    `unknown` the rules of a layout the runner cannot evaluate.
    """

    kind: ComponentKind
    name: str
    digest: str
    modified_at: str | None = None
    modified_by: str | None = None
    table: str | None = None
    screens: frozenset[str] = frozenset()
    unknown: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.name.lower()


@dataclass(frozen=True)
class Fingerprint:
    environment: Literal["uat", "production"]
    taken_at: datetime
    components: tuple[Component, ...]

    def by_key(self) -> dict[tuple[str, str], Component]:
        return {c.key: c for c in self.components}


@dataclass(frozen=True)
class Change:
    kind: ComponentKind
    name: str
    before: Component | None
    after: Component | None

    @property
    def who(self) -> str | None:
        return (self.after or self.before).modified_by  # type: ignore[union-attr]


def diff(baseline: Fingerprint, current: Fingerprint) -> list[Change]:
    """Every component added, removed or with another digest."""
    old, new = baseline.by_key(), current.by_key()
    changes: list[Change] = []
    for key in sorted(old.keys() | new.keys()):
        before, after = old.get(key), new.get(key)
        if before is None or after is None or before.digest != after.digest:
            ref = after or before
            assert ref is not None
            changes.append(Change(ref.kind, ref.name, before, after))
    return changes


@dataclass(frozen=True)
class Notice:
    level: Literal["info", "pause", "early_warning", "could_not_check"]
    text: str
    kinds: tuple[str, ...] = ()


@dataclass
class Reaction:
    """What the lane does: pause these kinds (with why), tell these things."""

    paused: dict[str, list[str]] = field(default_factory=dict)
    notices: list[Notice] = field(default_factory=list)

    def pause(self, kinds: Iterable[str], why: str) -> None:
        listed = sorted(kinds)
        for kind in listed:
            self.paused.setdefault(kind, []).append(why)
        if listed:
            self.notices.append(Notice("pause", why, tuple(listed)))


def _kinds(predicate: object, write_kinds: Mapping[str, WriteKind]) -> list[str]:
    return [k for k, w in write_kinds.items() if predicate(w)]  # type: ignore[operator]


def _depends(change: Change, write_kind: WriteKind) -> bool:
    ref = change.after or change.before
    assert ref is not None
    tables = {t.lower() for t in write_kind.tables}
    if change.kind in ("layout", "command"):
        return ref.name.lower() == write_kind.screen.lower()
    if change.kind == "template":
        return ref.name.lower() == write_kind.screen.lower() and write_kind.operation == "insert"
    if change.kind == "columns":
        return ref.name.lower() in tables
    if change.kind == "trigger":
        return (ref.table or "").lower() in tables
    if change.kind == "routine":
        return not ref.screens or write_kind.screen in ref.screens
    return True  # the context parser and the client version: every write


def react(
    changes: Iterable[Change],
    replays: Mapping[str, Replay],
    write_kinds: Mapping[str, WriteKind] = WRITE_KINDS,
) -> Reaction:
    """Ticket 65's table, row by row. `replays` is the replay of recorded
    saves on today's layouts, by screen; a screen absent has not run."""
    reaction = Reaction()
    for change in changes:
        who = f" ({change.who})" if change.who else ""
        dependent = _kinds(lambda w, c=change: _depends(c, w), write_kinds)
        if change.kind == "layout":
            after = change.after
            replay = replays.get(change.name, "not_run")
            if after is not None and after.unknown:
                reaction.pause(
                    dependent,
                    f"layout {change.name}{who}: rules DW cannot run: {', '.join(after.unknown)}",
                )
            elif after is None:
                reaction.pause(dependent, f"layout {change.name} was removed{who}")
            elif replay in ("agrees", "explained"):
                reaction.notices.append(
                    Notice(
                        "info",
                        f"DW follows Bravo's new layout {change.name}{who}",
                        tuple(dependent),
                    )
                )
            else:
                reaction.pause(
                    dependent,
                    f"layout {change.name}{who}: the replay has {replay.replace('_', ' ')}",
                )
        elif change.kind == "client_version":
            version = change.after.name if change.after else "?"
            reaction.pause(dependent, f"Bravo's client is now {version}: the replay must pass")
        else:
            reaction.pause(dependent, f"{change.kind} {change.name} changed{who}")
    return reaction


def early_warnings(uat: Fingerprint, production: Fingerprint) -> list[Notice]:
    """What UAT has that production does not yet: an upgrade tried first."""
    return [
        Notice(
            "early_warning",
            f"Bravo UAT has a different {c.kind} {c.name}; production does not yet",
        )
        for c in diff(production, uat)
    ]


def status(
    last_read: datetime | None,
    now: datetime,
    write_kinds: Mapping[str, WriteKind] = WRITE_KINDS,
) -> Reaction:
    """When Bravo could not be read: never "unchanged"; too old pauses all."""
    reaction = Reaction()
    if last_read is None:
        reaction.pause(write_kinds, "Bravo has never been read")
        return reaction
    reaction.notices.append(
        Notice("could_not_check", f"could not check since {last_read.isoformat()}")
    )
    if now - last_read > MAX_AGE:
        reaction.pause(write_kinds, f"Bravo not read for more than {MAX_AGE}")
    return reaction
