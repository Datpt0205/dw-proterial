"""A purchasing rule changed in words: the model proposes paths and values,
the platform's checks decide whether a draft exists, nothing applies, and
the draft carries a number nobody has used."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml

from dw_kernel.errors import DomainError, PermissionDeniedError
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.reapprovals import REAPPROVAL_REASON
from dw_purchasing.application.rule_drafting import RULE_CHANGE_IN_WORDS
from dw_purchasing.testing.world import World, caller, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
DATA = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_rule_words.json").read_text(encoding="utf-8")
)
_CONFIGURES = frozenset({PurchasingScopes.REQUEST_READ.value, PurchasingScopes.RULES_PROPOSE.value})


def _configurer() -> Any:
    return caller(scopes=_CONFIGURES, principal=uuid.UUID(int=0xC0F))


def _world() -> World:
    world = open_world(REPO, {})
    world.model.answers = DATA["answers"]
    return world


async def test_a_change_the_document_has_is_drafted_with_an_unused_number() -> None:
    world = _world()
    draft = await world.words.draft(_configurer(), "purchasing_rules", DATA["requests"]["limit"])
    assert draft.changed == ["approval.tiers.0.up_to"] and draft.problems == []
    assert draft.document is not None
    assert draft.document["approval"]["tiers"][0]["up_to"] == "50000000"
    base = draft.base_ref.partition("@")[2]
    assert draft.version is not None and draft.version != base
    assert draft.document["policy_version"] == draft.version
    # Nothing applies until a person sends it through the one door.
    assert world.store.versions == {}
    sent = await world.rules.propose(_configurer(), "purchasing_rules", draft.document)
    assert sent.status == "proposed"


async def test_a_path_the_document_lacks_refuses_the_whole_draft() -> None:
    world = _world()
    draft = await world.words.draft(
        _configurer(), "purchasing_rules", DATA["requests"]["injection"]
    )
    assert draft.document is None and draft.problems == ["path_unknown:approver"]


async def test_a_switch_past_its_ceiling_is_no_draft() -> None:
    world = _world()
    draft = await world.words.draft(
        _configurer(), "purchasing_automation", DATA["requests"]["switch"]
    )
    assert draft.document is None and draft.problems == ["document_invalid"]


async def test_without_the_scope_or_with_a_part_the_rule_lacks_nothing_is_read() -> None:
    world = _world()
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    with pytest.raises(PermissionDeniedError):
        await world.words.draft(reader, "purchasing_rules", "x")
    with pytest.raises(DomainError):
        await world.words.draft(_configurer(), "purchasing_rules", "x", focus="no_such_part")
    assert world.model.calls == []


@pytest.mark.parametrize(
    ("prompt", "variables"),
    [
        (RULE_CHANGE_IN_WORDS, ["rule_name", "document", "paths", "request"]),
        (REAPPROVAL_REASON, ["facts"]),
    ],
)
def test_the_prompt_files_are_the_ones_the_steps_name(prompt: Any, variables: list[str]) -> None:
    name = prompt.prompt_id.removeprefix("purchasing.")
    path = REPO / "configs/prompts/purchasing" / f"{name}@{prompt.version}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert (raw["prompt_id"], raw["version"]) == (prompt.prompt_id, prompt.version)
    assert raw["variables"] == variables
