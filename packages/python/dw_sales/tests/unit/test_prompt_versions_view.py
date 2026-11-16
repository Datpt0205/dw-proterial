"""The head's page of the prompt versions (ticket 43): each version the
optimiser proposed beside the one in force, with its replay figures and the
decided lines it shows, read by whoever decides them and nobody else.

The proposal comes from the lane itself (`test_prompt_optimiser.Bench`), so
what the page shows is what the lane stored, not a fixture shaped for it.
"""

from __future__ import annotations

import uuid

import pytest

from dw_kernel.errors import PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_sales.application.access import Gate
from dw_sales.application.ports import SalesScope
from dw_sales.application.prompt_versions import (
    PLATFORM_PROMPT,
    PromptDemonstrations,
    PromptVersionsService,
)
from dw_sales.evals.world import ALPHA, BETA

from .test_examples import GREEN, decided
from .test_prompt_optimiser import Bench

pytestmark = pytest.mark.unit

HEAD = uuid.UUID(int=0x4E1D)


def head(
    scope: SalesScope, scopes: frozenset[str] = frozenset({"sales.rules.approve"})
) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=HEAD,
        roles=frozenset(),
        scopes=scopes,
        plan_id="business",
    )


def service(bench: Bench) -> PromptVersionsService:
    return PromptVersionsService(bench.store, Gate(ScopeAuthorizationService()), bench.book)


async def test_the_head_sees_the_proposal_beside_the_version_in_force() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    assert (await bench.optimiser().tick(ALPHA)).reason == "proposed"

    view = await service(bench).list(head(ALPHA))

    # In force: the platform's prompt, which shows no decided line.
    assert (view.in_force, view.layer, view.demonstrations) == (PLATFORM_PROMPT.ref, "platform", [])
    assert view.step == "description_attributes"
    assert view.prompt == "sales.description_attributes@1.1.0"
    (version,) = view.versions
    assert version.status == "proposed" and version.approval_id is not None
    assert version.replay is not None
    assert (version.replay.cases, version.replay.right_before, version.replay.right_after) == (
        20,
        0,
        19,
    )
    # Which decided line it came from: the newest of the customer's, its
    # labelled case, its order and its customer.
    newest = decided(20, GREEN, "HW-1011")
    (shown,) = version.demonstrations
    assert (shown.description, shown.prv_code) == (GREEN, "HW-1011")
    assert (shown.label_id, shown.case_id, shown.customer_code) == (
        newest.label_id,
        newest.case_id,
        "C001",
    )


async def test_where_a_line_came_from_is_never_shown_to_a_reading() -> None:
    """The source fields are the head's; a reading is shown the description
    and the kept item's attributes only (`shown_lines`)."""
    bench = Bench()
    bench.decide(ALPHA)
    await bench.optimiser().tick(ALPHA)
    newest = decided(20, GREEN, "HW-1011")

    sent = "".join(str(dict(inputs)) for _, inputs in bench.model.calls)

    assert GREEN in sent
    for hidden in (str(newest.label_id), str(newest.case_id), "C001"):
        assert hidden not in sent


async def test_a_caller_without_the_heads_scope_is_refused() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    await bench.optimiser().tick(ALPHA)

    # Proposing rules is not deciding them: the demonstrations carry
    # customers' words.
    with pytest.raises(PermissionDeniedError):
        await service(bench).list(head(ALPHA, frozenset({"sales.rules.propose"})))


async def test_another_tenants_head_sees_none_of_this_tenants_versions() -> None:
    bench = Bench()
    bench.decide(ALPHA)
    await bench.optimiser().tick(ALPHA)

    view = await service(bench).list(head(BETA))

    assert view.versions == [] and view.layer == "platform"


def test_a_version_stored_before_its_lines_named_their_source_still_reads() -> None:
    stored = {
        "schema_version": "1.0",
        "policy_id": "sales_prompt_description_attributes",
        "policy_version": "1.2.0",
        "demonstrations": [{"description": GREEN, "prv_code": "HW-1011"}],
        "replay": None,
    }
    (line,) = PromptDemonstrations.model_validate(stored).demonstrations
    assert (line.label_id, line.case_id, line.customer_code) == (None, None, None)
