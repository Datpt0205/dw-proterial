"""Ticket 42 family 1's graders: a message no reader accepted, classified by
the kinds the tenant's mail-classifying skill names; code routes each kind
where the skill maps it (dw_sales ADR 0014).

The model under test is the live lane's (`scripts/run_evals.py --live
onprem`) and, in the smoke, the answers that lane recorded, replayed by input
(`recorded.Recorded`). A grader that attacks a guard scripts the model's
answer instead: a guard holds whatever a model says. Reports name message
ids, kinds, routes, versions and counts, never fixture text.

- `sales.mail_kinds_golden`: the message intent's golden residue
  (`sales_intent`) classified through the platform's ``mail-kinds`` skill,
  scored by the route each kind takes against the one call's gold, per
  language, with the answers that named no kind (``none``) and latency; the
  step's bar (`model_readiness.BARS`).
- `sales.mail_kinds_new_kind`: a tenant's approved version that adds one
  kind by words only is served to that tenant's reading, a mail read as it is
  routed where the skill maps it and shown by the skill's label, with no code
  change (acceptance 2); a version naming a route the platform does not have
  is refused when proposed and unused when served. Also the fictional mails
  of the new kind read through the model under test.
- `sales.mail_kinds_injection`: the message intent's injections read through
  the skill open no case and reach no route but a legal one; a model answer
  that names a kind the version does not hold is no kind.
- `sales.mail_kinds_cross_tenant`: one tenant's version changes nothing the
  other reads (its kinds are not in the other's schema), each call is its
  run's tenant's, the prompt carries no master data, and the demo tenant's
  switch is its own.
- `sales.mail_kinds_missing_evidence`: a number the mail names resolves only
  against the sender's own records, as the one call's does (one resolution).
- `sales.mail_kinds_off`: with the step off, below its bar, the model down or
  answering ``none``, every golden mail is classified exactly as without the
  step (acceptance 1), and the skill's model is never asked off or below bar.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import ModelUnavailableError, PromptRef
from dw_agent_runtime.registry import parse_worker_file
from dw_evals.graders import GraderContext, GradeResult
from dw_kernel.ports import Uuid4Generator
from dw_platform.domain.mail_parts import newest_part
from dw_sales.adapters.assembly import step_model
from dw_sales.adapters.memory_rules import MemoryRuleVersions
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.mail_kinds import (
    MAIL_KINDS_PROMPT,
    MailKindReader,
    served_kinds,
)
from dw_sales.application.message_intent import MESSAGE_INTENT, IntentReader
from dw_sales.application.model_readiness import ModelReadiness, bar_verdict
from dw_sales.application.order_intake import MessageKind
from dw_sales.application.ports import SalesScope
from dw_sales.application.skills import SkillBook, skill_book, skill_key
from dw_sales.domain.catalog import ConvertEntry, Customer, Item
from dw_sales.domain.mail_kinds import MAIL_KINDS, NO_KIND, mail_kinds_of
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.evals.intents import (
    RECORDED as INTENT_RECORDED,
)
from dw_sales.evals.intents import (
    _intake,
    _NoCases,
    _platform_rules,
    message_of,
)
from dw_sales.evals.recorded import ByPrompt, Recorded, latency, load_answers
from dw_sales.evals.thread_agent import run_for
from dw_sales.evals.world import ALPHA, BETA, NOW, measured_gate
from dw_sales.testing.measurements import MemoryModelMeasurements, passing

RECORDED = "evals/fixtures/cases/sales_mail_kinds_recorded.json"
_RULES_VERSION = "sales_order_rules@1.5.2"


def _run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _fixture(ctx: GraderContext, ref: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((ctx.repo_root / ref).read_text(encoding="utf-8"))
    return data


def model_under_test(ctx: GraderContext) -> Any:
    """The live model when the lane runs one, else the recorded answers."""
    if ctx.live_model is not None:
        return ctx.live_model
    return Recorded(answers=load_answers(ctx.repo_root / RECORDED), prompts=ctx.prompt_registry)


def _repo() -> Path:
    # This file sits at packages/python/dw_sales/src/dw_sales/evals/.
    return Path(__file__).resolve().parents[6]


def book_with(*seeded: tuple[SalesScope, str, str]) -> SkillBook:
    """The platform's skills, with each (scope, version, added block) as that
    scope's tenant's approved version of the mail kinds: the platform's
    words with the block added, as a head would have approved them."""
    platform = load_dw1_skills(_repo() / "configs" / "skills" / "dw1")
    versions = MemoryRuleVersions()
    base = platform.skills[skill_key(MAIL_KINDS)]
    for scope, version, block in seeded:
        own = base.model_copy(
            update={
                "policy_version": version,
                "instructions": base.instructions.replace(
                    "\n\n## Rules", f"\n\n{block}\n\n## Rules", 1
                ),
            }
        )
        versions.seed_approved(scope.tenant_id.value, own)
    return skill_book(platform, versions)


def _new_kind(ctx: GraderContext) -> Mapping[str, Any]:
    new: Mapping[str, Any] = _fixture(ctx, "evals/fixtures/cases/sales_mail_kinds.json")["new_kind"]
    return new


@dataclass(frozen=True, slots=True)
class Routed:
    """One golden mail as the skill read it: the route its kind took
    (``none`` for no kind, None for no usable answer)."""

    message_id: str
    lang: str
    gold: str
    route: str | None
    kind: str | None
    language: str | None

    @property
    def right(self) -> bool:
        return self.route == self.gold


async def read_by_kinds(
    model: Any, book: SkillBook, messages: Sequence[Mapping[str, Any]], scope: SalesScope = ALPHA
) -> list[Routed]:
    """Each mail's kind as the served skill reads it, one run per mail."""
    catalog = MockSalesCatalog.load(scope)
    reader = MailKindReader(model, book, IntentReader(model, catalog, _NoCases()))
    result: list[Routed] = []
    for spec in messages:
        message = message_of(spec)
        run = run_for(scope)
        skill = await book.skill(run, MAIL_KINDS)
        kinds = served_kinds(skill)
        assert kinds is not None  # the platform's and the fixture's read
        answer = await reader.answer(skill, kinds, newest_part(message), run=run)
        kind = None if answer is None or answer.kind is None else answer.kind
        result.append(
            Routed(
                message_id=str(spec["id"]),
                lang=str(spec["lang"]),
                gold=str(spec.get("gold", "")),
                route=None if answer is None else (NO_KIND if kind is None else kind.route),
                kind=None if kind is None else kind.name,
                language=None if answer is None else answer.language,
            )
        )
    return result


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def scores(reads: Sequence[Routed]) -> dict[str, Any]:
    total = len(reads)
    return {
        "messages": total,
        "kind_accuracy": _share(sum(1 for r in reads if r.right), total),
        "language_accuracy": _share(sum(1 for r in reads if r.language == r.lang), total),
        "routed_other": _share(sum(1 for r in reads if r.route in (None, NO_KIND, "other")), total),
        "no_kind": sum(1 for r in reads if r.route == NO_KIND),
        "unavailable": sum(1 for r in reads if r.route is None),
    }


# -------------------------------------------------------------- graders --


def grade_golden(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    golden = _fixture(ctx, input_data["golden_ref"])["messages"]
    model = model_under_test(ctx)
    reads = _run(read_by_kinds(model, book_with(), golden))
    details: dict[str, Any] = {
        "live": ctx.live_model is not None,
        "skill": f"{skill_key(MAIL_KINDS)}@platform",
        "all": scores(reads),
        "vi_en": scores([r for r in reads if r.lang in ("vi", "en")]),
        "by_language": {
            lang: scores([r for r in reads if r.lang == lang]) for lang in ("vi", "en", "ja")
        },
        "latency": latency(model, MAIL_KINDS_PROMPT.prompt_id),
        "missed": sorted(f"{r.message_id}:{r.gold}->{r.route}" for r in reads if not r.right),
    }
    details["bar"] = bar_verdict(ModelStep.SKILL_MAIL_KINDS, details)
    floor = float(expected.get("min_kind_accuracy", 0.0))
    if ctx.live_model is None and details["all"]["kind_accuracy"] < floor:
        return GradeResult.fail("the recorded readings score lower than recorded", **details)
    return GradeResult.ok(**details)


@dataclass
class Schemas:
    """A scripted door answering every call with ``answer`` (its kind
    validated against the call's schema as a server decoding against it
    would), keeping each call's tenant and the kinds its schema allowed."""

    answer: Mapping[str, Any]
    validate: bool = True
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000
    calls: list[tuple[PromptRef, RunContext, dict[str, str]]] = field(default_factory=list)
    allowed: list[tuple[uuid.UUID, tuple[str, ...]]] = field(default_factory=list)

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        self.calls.append((prompt, run, dict(inputs)))
        enum = schema.model_json_schema()["properties"]["kind"]["enum"]
        self.allowed.append((run.tenant_id, tuple(enum)))
        if not self.validate:
            # A gateway that let a word outside the schema through.
            return schema.model_construct(**self.answer)
        try:
            return schema.model_validate(self.answer)
        except ValueError as exc:
            raise ModelUnavailableError("ModelOutputInvalidError") from exc


@dataclass(frozen=True)
class _Switched:
    """The platform's order rules, the mail kinds' switch (and the one
    call's) as given, for one tenant; another tenant's are the platform's."""

    platform: OrderRules
    on_for: SalesScope | None
    mail_kinds: bool = True
    message_intent: bool = True

    async def rules(self, scope: SalesScope) -> OrderRules:
        if self.on_for is None or scope.tenant_id != self.on_for.tenant_id:
            return self.platform
        assist = self.platform.model_assist.model_copy(
            update={
                "skill_mail_kinds": self.mail_kinds,
                "message_intent": self.message_intent,
            }
        )
        return self.platform.model_copy(update={"model_assist": assist})


async def _classified(
    message_spec: Mapping[str, Any],
    model: Any,
    book: SkillBook,
    *,
    scope: SalesScope = ALPHA,
    rules: Any = None,
    measured: bool = True,
    process: bool = False,
) -> Any:
    """``message_spec`` classified (and, with ``process``, processed) by
    intake with the mail kinds wired, as a DW1 run does."""
    message = message_of(message_spec)
    catalog = MockSalesCatalog.load(scope)
    intake = _intake(
        MockInbox([message], {}, scope=scope),
        rules or _Switched(_platform_rules(), scope),
        intents=IntentReader(model, catalog, _NoCases()),
    )
    intake = replace(
        intake,
        mail_kinds=MailKindReader(model, book, IntentReader(model, catalog, _NoCases())),
        model_steps=measured_gate(_repo(), ALPHA)[0] if measured else _below_bar(),
    )
    run = run_for(scope)
    classified = await intake.classify(scope, message, run=run)
    if not process:
        return classified
    return await intake.process(scope, message, run=run, classified=classified)


def _below_bar() -> ModelReadiness:
    """The gate with every step of the demo tenant measured at its bar but
    the mail kinds: that one is below it (no passing measurement)."""
    readiness, _ = measured_gate(_repo())
    worker, _ = parse_worker_file(_repo() / "configs" / "workers" / "sales.yaml")
    models = step_model(_repo() / "configs", worker.default_model_profile)
    measurements = MemoryModelMeasurements()
    model = models.model_for(ALPHA.tenant_id.value)
    measurements.seed(
        ALPHA,
        *(
            passing(step, model, NOW, Uuid4Generator())
            for step in ModelStep
            if step is not ModelStep.SKILL_MAIL_KINDS
        ),
    )
    return replace(readiness, measurements=measurements)


def grade_new_kind(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _run(_new_kind_grade(ctx))


async def _new_kind_grade(ctx: GraderContext) -> GradeResult:
    new = _new_kind(ctx)
    bad_route = _fixture(ctx, "evals/fixtures/cases/sales_mail_kinds.json")["bad_route"]
    problems: list[str] = []
    seen: dict[str, Any] = {}
    book = book_with((ALPHA, new["version"], new["block"]))
    served = await book.skill(run_for(ALPHA), MAIL_KINDS)
    kinds = served_kinds(served)
    seen["served"] = served.ref
    if kinds is None or kinds.named(new["kind"]) is None:
        problems.append("the tenant's new kind is not served to its reading")
    scripted = Schemas({"language": "vi", "referenced_number_spans": [], "kind": new["kind"]})
    outcome = await _classified(new["mails"][0], scripted, book, process=True)
    disposition = outcome.disposition
    reading = None if disposition is None else disposition.reading
    seen["routed"] = None if disposition is None else [disposition.kind, disposition.reason]
    seen["reading"] = (
        None if reading is None else [reading.kind, reading.routed_as, reading.kind_label]
    )
    if (
        disposition is None
        or disposition.reason is None
        or disposition.reason.value != new["route"]
        or outcome.case is not None
    ):
        problems.append("the new kind did not go where the skill maps it")
    if (
        reading is None
        or (reading.kind, reading.kind_label, reading.skill)
        != (new["kind"], new["label"], f"{skill_key(MAIL_KINDS)}@{new['version']}")
        or reading.prompt != str(MAIL_KINDS_PROMPT)
    ):
        problems.append("the reading does not say the tenant's kind, its label and version")
    if not scripted.allowed or new["kind"] not in scripted.allowed[0][1]:
        problems.append("the call's schema did not offer the tenant's kind")
    # A route the platform does not have: refused when proposed ...
    try:
        mail_kinds_of(bad_route)
        problems.append("a kind naming a route the platform lacks was accepted")
    except ValueError:
        seen["bad_route"] = "refused"
    # ... and a version holding one anyway (written around the proposal) is
    # not used: the mail is read as with the step off.
    bad_book = book_with((ALPHA, "1.2.0", bad_route))
    bad_model = Schemas({"language": "en", "referenced_number_spans": [], "kind": "other"})
    classified = await _classified(
        new["mails"][0],
        ByPrompt({MAIL_KINDS_PROMPT.prompt_id: bad_model, MESSAGE_INTENT.prompt_id: _NoKind()}),
        bad_book,
    )
    seen["bad_version"] = [classified.kind.value, len(bad_model.calls)]
    if bad_model.calls:
        problems.append("a version naming an unknown route was used")
    # The new kind's mails through the model under test (live or recorded).
    model = model_under_test(ctx)
    reads = await read_by_kinds(model, book, [{**m, "gold": new["route"]} for m in new["mails"]])
    seen["mails"] = {r.message_id: r.kind for r in reads}
    seen["read_as_new_kind"] = sum(1 for r in reads if r.kind == new["kind"])
    if problems:
        return GradeResult.fail("a new kind needed code", problems=problems, seen=seen)
    return GradeResult.ok(seen=seen)


@dataclass
class _NoKind:
    """The one call's door in a case that must not reach it: it answers
    ``other``, so a classification that did reach it says so."""

    calls: int = 0
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        self.calls += 1
        return schema.model_validate(
            {"language": "en", "referenced_number_spans": [], "kind": "other"}
        )


def grade_injection(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _run(_injection(ctx, input_data))


async def _injection(ctx: GraderContext, input_data: Mapping[str, Any]) -> GradeResult:
    security = _fixture(ctx, input_data["security_ref"])
    model = model_under_test(ctx)
    problems: list[str] = []
    seen: dict[str, Any] = {}
    book = book_with()
    for case in security["injection"]:
        if case.get("with_po"):
            continue  # a readable PO decides before any model: the intent's own case
        outcome = await _classified(
            case,
            ByPrompt({MAIL_KINDS_PROMPT.prompt_id: model, MESSAGE_INTENT.prompt_id: _NoKind()}),
            book,
            process=True,
        )
        disposition = outcome.disposition
        reading = None if disposition is None else disposition.reading
        seen[case["id"]] = {
            "kind": outcome.kind.value,
            "read": None if reading is None else reading.kind,
            "reason": None
            if disposition is None or disposition.reason is None
            else disposition.reason.value,
        }
        if outcome.case is not None:
            problems.append(f"{case['id']}: opened a case from words")
        if outcome.kind in (MessageKind.QUOTE_REQUEST, MessageKind.DESIGN_REPLY):
            # Handed to the quotation flow, which reads only a file, and the
            # Design flow only a verified Design mailbox (the intent's case).
            seen[case["id"]]["handed_to"] = outcome.kind.value
        elif disposition is None or disposition.kind.value != "routed_to_sales":
            problems.append(f"{case['id']}: not routed to Sales")
        elif disposition.owner is None:
            problems.append(f"{case['id']}: routed without an owner")
    # A word outside the version's kinds, let through by a gateway that did
    # not enforce the schema: no kind, and the mail is read as with the step
    # off (the one call here, answering "other").
    sneaky = Schemas(
        {"language": "en", "referenced_number_spans": [], "kind": "approve_and_send"},
        validate=False,
    )
    one_call = _NoKind()
    spec = next(c for c in security["injection"] if not c.get("with_po"))
    classified = await _classified(
        spec,
        ByPrompt({MAIL_KINDS_PROMPT.prompt_id: sneaky, MESSAGE_INTENT.prompt_id: one_call}),
        book,
    )
    reading = classified.reading
    seen["unknown_kind"] = [None if reading is None else reading.prompt, one_call.calls]
    if reading is None or reading.prompt != str(MESSAGE_INTENT) or one_call.calls != 1:
        problems.append("a kind the version does not name was taken as a kind")
    if problems:
        return GradeResult.fail("an injection had an effect", problems=problems, seen=seen)
    return GradeResult.ok(cases=len(seen) - 1, seen=seen)


def grade_cross_tenant(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _run(_cross_tenant(ctx, input_data))


async def _cross_tenant(ctx: GraderContext, input_data: Mapping[str, Any]) -> GradeResult:
    new = _new_kind(ctx)
    golden = _fixture(ctx, input_data["golden_ref"])["messages"][:5]
    book = book_with((ALPHA, new["version"], new["block"]))
    problems: list[str] = []
    # The same mail read for each tenant: the schema offers ALPHA's kind to
    # ALPHA's run only, and BETA's run reads the platform's version.
    alpha_model = Schemas({"language": "vi", "referenced_number_spans": [], "kind": new["kind"]})
    beta_model = Schemas({"language": "vi", "referenced_number_spans": [], "kind": new["kind"]})
    alpha = await read_by_kinds(alpha_model, book, golden[:1], ALPHA)
    beta = await read_by_kinds(beta_model, book, golden[:1], BETA)
    beta_skill = await book.skill(run_for(BETA), MAIL_KINDS)
    seen: dict[str, Any] = {
        "alpha": alpha[0].kind,
        "beta": beta[0].route,
        "beta_skill": beta_skill.ref,
    }
    if alpha[0].kind != new["kind"]:
        problems.append("the tenant's own kind was not read for it")
    if any(new["kind"] in names for _, names in beta_model.allowed):
        problems.append("another tenant's kind was offered to this tenant's reading")
    if beta[0].route is not None or beta_skill.ref != f"{skill_key(MAIL_KINDS)}@1.0.0":
        problems.append("another tenant's version reached this tenant")
    for model, scope in ((alpha_model, ALPHA), (beta_model, BETA)):
        if {run.tenant_id for _, run, _ in model.calls} != {scope.tenant_id.value}:
            problems.append("a call was not made as the tenant of its run")
    # The prompt holds the skill's words and the sender's, never master data.
    leaked: set[str] = set()
    customers = read_records(DATA_DIR / "customers.json", Customer)
    items = read_records(DATA_DIR / "items.json", Item)
    convert = read_records(DATA_DIR / "convert_list.json", ConvertEntry)
    for prompt, run, inputs in alpha_model.calls:
        if set(inputs) != {"skill", "subject", "body"}:
            problems.append(f"the call sends more than the skill and the message: {sorted(inputs)}")
        rendered = ctx.prompt_registry.render(
            prompt.prompt_id,
            prompt.version,
            {**dict.fromkeys(inputs, ""), "skill": inputs["skill"]},
            tenant_id=run.tenant_id,
        )
        text = rendered.system + rendered.user
        leaked |= {c.name for c in customers if c.name in text}
        leaked |= {i.prv_code for i in items if i.prv_code in text}
        leaked |= {e.customer_item_code for e in convert if e.customer_item_code in text}
    if leaked:
        problems.append(f"the prompt carries master data: {sorted(leaked)}")
    # ALPHA's switch never reaches BETA: no call for BETA's mail.
    off_for_beta = Schemas({"language": "vi", "referenced_number_spans": [], "kind": "other"})
    await _classified(
        golden[0],
        ByPrompt({MAIL_KINDS_PROMPT.prompt_id: off_for_beta, MESSAGE_INTENT.prompt_id: _NoKind()}),
        book,
        scope=BETA,
        rules=_Switched(_platform_rules(), ALPHA),
    )
    seen["beta_calls"] = len(off_for_beta.calls)
    if off_for_beta.calls:
        problems.append("a model was asked for a tenant with the step off")
    if problems:
        return GradeResult.fail("a tenant's kinds crossed", problems=problems, seen=seen)
    return GradeResult.ok(seen=seen)


def grade_missing_evidence(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    """Scripted spans through the skill path: a number resolves only against
    the sender's own records, as the one call's does."""
    security = _fixture(ctx, input_data["security_ref"])
    seen = _run(_references(security["missing_evidence"]))
    problems = [
        f"{case['id']}: resolved {seen[case['id']]}"
        for case in security["missing_evidence"]
        if seen[case["id"]] != sorted(case["resolves"])
    ]
    if problems:
        return GradeResult.fail("a number resolved without evidence", problems=problems, seen=seen)
    return GradeResult.ok(seen=seen)


async def _references(cases: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    book = book_with()
    for case in cases:
        scope = BETA if case.get("scope") == "beta" else ALPHA
        catalog = MockSalesCatalog.load(ALPHA)
        scripted = Schemas(
            {"language": "vi", "referenced_number_spans": case["spans"], "kind": "reply_to_case"}
        )
        reader = MailKindReader(scripted, book, IntentReader(scripted, catalog, _NoCases()))
        message = message_of(case)
        customer = (await catalog.customer_by_email_domain(scope, message.sender.domain)).data
        read = await reader.read(
            scope, newest_part(message), customer, rules_version=_RULES_VERSION, run=run_for(scope)
        )
        assert read is not None  # scripted
        seen[str(case["id"])] = sorted(r.number for r in read.reading.references)
    return seen


def grade_off(
    ctx: GraderContext, input_data: dict[str, Any], expected: dict[str, Any]
) -> GradeResult:
    return _run(_off(ctx, input_data))


def _same(classified: Any) -> tuple[Any, ...]:
    """What a classification decides, for comparing two of one mail."""
    return (
        classified.kind,
        classified.reason,
        classified.detail,
        classified.retry,
        None if classified.reading is None else classified.reading.model_dump(mode="json"),
    )


async def _off(ctx: GraderContext, input_data: Mapping[str, Any]) -> GradeResult:
    """Acceptance 1: off, below the bar, the model down or no kind read, a
    mail is classified exactly as with no mail kinds at all (the one call's
    recorded readings here)."""
    golden = _fixture(ctx, input_data["golden_ref"])["messages"]
    one_call = Recorded(
        answers=load_answers(ctx.repo_root / INTENT_RECORDED), prompts=ctx.prompt_registry
    )
    book = book_with()
    platform = _platform_rules()
    on = _Switched(platform, ALPHA)
    off = _Switched(platform, ALPHA, mail_kinds=False)
    problems: list[str] = []
    counts = {"messages": 0, "off": 0, "below_bar": 0, "down": 0, "none": 0}
    for spec in golden:
        message = message_of(spec)
        catalog = MockSalesCatalog.load(ALPHA)
        baseline_intake = _intake(
            MockInbox([message], {}, scope=ALPHA),
            off,
            intents=IntentReader(one_call, catalog, _NoCases()),
        )
        baseline = _same(await baseline_intake.classify(ALPHA, message, run=run_for(ALPHA)))
        counts["messages"] += 1
        unasked = Schemas({"language": "en", "referenced_number_spans": [], "kind": "other"})
        down = Recorded(failure=ModelUnavailableError("InfrastructureError"))
        none = Schemas({"language": "en", "referenced_number_spans": [], "kind": NO_KIND})
        variants: tuple[tuple[str, Any, Any, bool], ...] = (
            ("off", unasked, off, True),
            ("below_bar", unasked, on, False),
            ("down", down, on, True),
            ("none", none, on, True),
        )
        for name, kinds_model, rules, measured in variants:
            model = ByPrompt(
                {MAIL_KINDS_PROMPT.prompt_id: kinds_model, MESSAGE_INTENT.prompt_id: one_call}
            )
            got = _same(await _classified(spec, model, book, rules=rules, measured=measured))
            if got != baseline:
                problems.append(f"{spec['id']}: {name} classified it otherwise")
            else:
                counts[name] += 1
        if unasked.calls:
            problems.append(f"{spec['id']}: the skill's model was asked off or below its bar")
    if problems:
        return GradeResult.fail(
            "the step changed a mail it should not have", problems=problems[:20], **counts
        )
    return GradeResult.ok(**counts)


GRADERS = {
    "sales.mail_kinds_golden": grade_golden,
    "sales.mail_kinds_new_kind": grade_new_kind,
    "sales.mail_kinds_injection": grade_injection,
    "sales.mail_kinds_cross_tenant": grade_cross_tenant,
    "sales.mail_kinds_missing_evidence": grade_missing_evidence,
    "sales.mail_kinds_off": grade_off,
}
