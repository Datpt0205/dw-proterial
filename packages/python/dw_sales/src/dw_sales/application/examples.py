"""Past decided cases shown to a model step as examples (ticket 43 part 2,
dw_sales ADR 0015 decision 5).

A description a customer wrote before, and the item a person chose for it,
is the best evidence of what that customer's words mean. A reading of a new
line is shown the decided lines most like it, the same customer's first. The
step is `description_attributes`: it has the most labelled cases (one per
line a person settled, where `po_body_extraction` has one per field a person
typed over) and its input is one short line, cheap to embed and to show.

- **What an example is**: a labelled case of the step whose verdict says a
  person kept a value (confirmed or corrected; never a rejection, never a
  model's answer nobody confirmed), the newest one of its line, with the
  line's description read back from the order it came from.
- **Where it is found**: `ExampleIndexPort`, the knowledge gateway's examples
  index (`dw_knowledge.examples.ExampleGateway`, satisfied at the composition
  root). Its filter is the run's tenant and workspace and the step; the
  customer is the case's resolved one. It returns ids only.
- **Where it is read**: `DescriptionExamplesPort`, PostgreSQL under the
  scope's RLS. An id another tenant's index gave back reads as nothing.
- **Never on the mail's critical path for long**: the search is bounded by
  the gateway's timeout and every failure (the embedder, the index, the read)
  is a reading without examples, logged, never a refusal of the mail.
- **The index is filled by the worker** (`ExampleIndexLane`, the
  `sales_examples` lane), after the decision committed: a case not indexed yet
  is not shown yet, nothing worse.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import CustomerCode, PrvCode
from dw_sales.domain.description_reading import SpanRead
from dw_sales.domain.order_checks import ModelStep

_LOG = logging.getLogger("dw_sales.examples")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The step whose decided cases are examples (module docstring).
STEP: Final = ModelStep.DESCRIPTION_ATTRIBUTES
# The most examples one reading is shown, whatever k and the lines: each is a
# line of a prompt every line of the call carries.
MAX_SHOWN: Final = 12
# What the lane indexes per read.
INDEX_PAGE: Final = 200
# The lane that fills the index (`apps/worker`).
EXAMPLES_LANE: Final = "sales_examples"


class DescriptionExample(BaseModel):
    """One decided line: what the customer wrote, the item a person kept.

    It carries the properties the examples index takes
    (`dw_knowledge.examples.ExampleText`, matched by shape: this context
    imports no knowledge module): the id is the labelled case's, the subject
    the customer, the group the order case (a replay or an eval never
    retrieves its own order), the text the description, which is all that is
    embedded."""

    model_config = _FROZEN

    label_id: uuid.UUID
    case_id: uuid.UUID
    customer_code: CustomerCode | None
    decided_at: AwareDatetime
    description: str = Field(min_length=1, max_length=500)
    prv_code: PrvCode
    # The model's reading of the line that code accepted, where one was
    # stored; shown as the answer it was only where it fits the kept item
    # (`model_reading.shown_lines`). Never embedded.
    spans: tuple[SpanRead, ...] = ()

    @property
    def example_id(self) -> uuid.UUID:
        return self.label_id

    @property
    def step(self) -> str:
        return STEP.value

    @property
    def subject(self) -> str | None:
        return self.customer_code

    @property
    def group(self) -> str:
        return str(self.case_id)

    @property
    def text(self) -> str:
        return self.description


class DescriptionExamplesPort(Protocol):
    """The decided description lines of one workspace, under its RLS."""

    async def by_ids(
        self, scope: SalesScope, ids: Sequence[uuid.UUID]
    ) -> Sequence[DescriptionExample]:
        """The examples among ``ids`` this scope holds, in no particular
        order; an id it does not hold, or no longer an example (rejected
        since, or its month dropped), is left out."""
        ...

    async def after(
        self, scope: SalesScope, position: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> Sequence[DescriptionExample]:
        """The examples decided after ``position`` (decided_at, label id),
        oldest first, at most ``limit``: what the index lane reads on."""
        ...


class ExampleIndexPort(Protocol):
    """The examples index (`dw_knowledge.examples.ExampleGateway`)."""

    async def similar(
        self,
        texts: Sequence[str],
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        step: str,
        subject: str | None,
        k: int,
        exclude_groups: Sequence[str] = (),
    ) -> list[list[uuid.UUID]]: ...

    async def add(
        self,
        examples: Sequence[DescriptionExample],
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class Lookup:
    """What one reading asks for: the case's resolved customer (never a
    model's word), how many per line (the tenant's rules), and the order
    cases never to show (the one being replayed)."""

    customer_code: str | None
    per_line: int
    exclude_cases: tuple[uuid.UUID, ...] = ()


@dataclass
class ExampleFinder:
    """The decided lines most like a reading's lines, or none on any failure."""

    index: ExampleIndexPort
    examples: DescriptionExamplesPort
    # Seconds each finished search took, newest last, at most `_KEPT`: what
    # an eval and the process's own log read the added latency from.
    timings: list[float] = field(default_factory=list)

    async def find(
        self, scope: SalesScope, descriptions: Sequence[str], lookup: Lookup
    ) -> list[DescriptionExample]:
        """Up to `lookup.per_line` per description, interleaved (each line's
        nearest first, then each line's second), deduplicated, at most
        `MAX_SHOWN`. Empty when nothing is asked, and on any failure."""
        if lookup.per_line <= 0 or not descriptions:
            return []
        started = time.perf_counter()
        try:
            ranked = await self.index.similar(
                list(descriptions),
                tenant_id=scope.tenant_id.value,
                workspace_id=scope.workspace_id.value,
                step=STEP.value,
                subject=lookup.customer_code,
                k=lookup.per_line,
                exclude_groups=[str(case) for case in lookup.exclude_cases],
            )
            order: list[uuid.UUID] = []
            for rank in range(lookup.per_line):
                for ids in ranked:
                    if rank < len(ids) and ids[rank] not in order:
                        order.append(ids[rank])
            order = order[:MAX_SHOWN]
            found = (
                {e.label_id: e for e in await self.examples.by_ids(scope, order)} if order else {}
            )
        except Exception as exc:
            # Broad on purpose: whatever failed, the mail is read as it was
            # before examples existed. The type only: a message can quote text.
            _LOG.warning(
                "examples unavailable; reading without", extra={"error": type(exc).__name__}
            )
            return []
        finally:
            self._timed(time.perf_counter() - started)
        excluded = set(lookup.exclude_cases)
        return [found[i] for i in order if i in found and found[i].case_id not in excluded]

    def _timed(self, seconds: float) -> None:
        self.timings.append(seconds)
        del self.timings[:-_KEPT]


_KEPT: Final = 1000


def p95(timings: Sequence[float]) -> float | None:
    """The 95th percentile of ``timings`` (nearest rank), None with none."""
    if not timings:
        return None
    ordered = sorted(timings)
    return ordered[max(0, -(-95 * len(ordered) // 100) - 1)]


@dataclass
class ExampleIndexLane:
    """One tick of the `sales_examples` lane in one workspace: index the
    examples decided since the last one indexed. The position is the
    process's own; after a restart it starts again from the oldest, and the
    index skips what it holds already (`ExampleGateway.add` asks it)."""

    examples: DescriptionExamplesPort
    index: ExampleIndexPort
    _positions: dict[SalesScope, tuple[datetime, uuid.UUID]] = field(default_factory=dict)

    async def tick(self, scope: SalesScope) -> int:
        indexed = 0
        while True:
            page = await self.examples.after(scope, self._positions.get(scope), INDEX_PAGE)
            if not page:
                return indexed
            indexed += await self.index.add(
                page, tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value
            )
            last = page[-1]
            self._positions[scope] = (last.decided_at, last.label_id)
            if len(page) < INDEX_PAGE:
                return indexed
