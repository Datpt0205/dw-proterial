"""A customer's reply in a case's thread: linked by its headers, read by a
model into thread intents where the tenant turns it on, and never applied
without Sales (tickets 32 and 26, dw_sales ADRs 0005 and 0010).

Over the in-memory world (`dw_sales.evals.world`), the services the API
serves, with a scripted model (`Recorded`): which case a reply joins and which
it never joins, what code keeps of a reading, the step it proposes and where,
and that keeping the PO as it is disposes no finding. The live model's
accuracy is the eval lane's (`sales_reply@2.0.0`).
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import ConflictError
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import (
    PROMPT_TOKENS,
    REPLY_INTENT,
    ReplyReader,
    reading_context,
)
from dw_sales.application.threads import ThreadIndex, ThreadLinks
from dw_sales.domain.catalog import Customer
from dw_sales.domain.dispositions import CaseKind, DispositionKind, MessageDisposition
from dw_sales.domain.orders import DispositionKind as FindingDisposition
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.domain.reply_intent import (
    INTENT_STEPS,
    ModelThreadIntents,
    ReplyReading,
    ThreadIntent,
    located_quotes,
    proposed_step,
    verified_intents,
)
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ACCEPT = "We accept the proposed specification without changes."
KEEP = "Please keep the PO as it is."
RUN = RunContext(
    run_id=uuid.UUID(int=0x32),
    tenant_id=ALPHA.tenant_id.value,
    workspace_id=ALPHA.workspace_id.value,
    actor_id=uuid.UUID(int=0xA1),
    worker_id="sales-dw1",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t32",
)


def _says(intent: ThreadIntent, *quotes: str) -> Recorded:
    return _saying((intent, quotes))


def _saying(*intents: tuple[ThreadIntent, tuple[str, ...]]) -> Recorded:
    """A scripted model answering every call with ``intents``, each with the
    sentences it copied."""
    return Recorded(raw={"intents": [{"quote_spans": list(q), "intent": i} for i, q in intents]})


def _world(model: Any = None, sample: SampleSet | None = None) -> World:
    return open_world(REPO, sample or SampleSet.of(REPO, None), CALLERS, model=model)


async def _spec_discussion(world: World) -> uuid.UUID:
    """M09's request taken to Design, M18's reply attached, and the spec put
    to the customer: the case M41 answers."""
    ((disposition, _),) = (await world.process_each(AN, ["M09"])).values()
    case_id = disposition.case_id
    assert case_id is not None
    commands, context = world.services.quote_commands, AN.context()

    def version() -> int:
        return world.quote(case_id).case_version

    await commands.ycbg(context, case_id, case_version=version(), ycbg_no=None)
    await commands.ycbg(context, case_id, case_version=version(), ycbg_no="YCBG-2609-028")
    await commands.design_sent(context, case_id, case_version=version())
    await world.process_each(AN, ["M18"])
    assert world.quote(case_id).status is QuoteStatus.DESIGN_REPLIED
    await commands.spec_discussion(context, case_id, case_version=version(), step="start")
    return case_id


async def _correction_requested(world: World) -> uuid.UUID:
    """M04 with both findings sent back to the customer: the case M42 answers."""
    ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
    case_id = disposition.case_id
    assert case_id is not None
    commands, context = world.services.order_commands, AN.context()
    for key in ("price_mismatch:2", "code_unmapped:3"):
        await commands.dispose(
            context,
            case_id,
            key,
            case_version=world.order(case_id).case_version,
            disposition="ask_customer",
        )
    await commands.request_correction(
        context, case_id, case_version=world.order(case_id).case_version
    )
    assert world.order(case_id).status is OrderStatus.CORRECTION_REQUESTED
    return case_id


# ----------------------------------------------------------- the thread --


async def test_a_reply_in_a_requests_thread_joins_its_case_whatever_its_subject_says() -> None:
    """M41's subject repeats "RFQ": the keyword tables made it a new request,
    which the quotation flow routed as unreadable. Its headers say whose reply
    it is, and no model is needed for that."""
    world = _world()
    case_id = await _spec_discussion(world)

    ((disposition, case),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.kind == "attached_to_case"
    assert (disposition.case_kind, disposition.case_id) == (CaseKind.QUOTE, case_id)
    assert disposition.reply is not None and disposition.reply.linked_to == "M09"
    assert disposition.reply.reading is None
    # Attaching changes nothing on the case: Sales takes any step.
    assert case is not None and case.status is QuoteStatus.SPEC_DISCUSSION


async def test_a_reply_to_a_message_on_no_case_is_classified_as_any_other_message() -> None:
    """M42 names M04's Message-ID; with M04 not processed there is no case to
    join, so its words route it, as before thread headers were read."""
    world = _world()

    ((disposition, _),) = (await world.process_each(AN, ["M42"])).values()

    assert (disposition.kind, disposition.reply) == ("routed_to_sales", None)


async def test_a_reply_naming_another_customers_message_is_not_attached() -> None:
    """Headers are the sender's to write: Quorilo naming Norvanta's message
    reaches no Norvanta case."""
    world = _world()
    await _correction_requested(world)
    m04 = await _sample(world, "M04")
    forged = _reply("ivy.tran@quorilo.example", (str(m04.internet_message_id),))
    own = _reply("hana.westbrook@norvanta.example", (str(m04.internet_message_id),))
    links = ThreadLinks(world.store, _Listed([m04]))

    assert await links.cases(ALPHA, forged, await _customer(world, "QRL")) == ()
    (linked,) = await links.cases(ALPHA, own, await _customer(world, "NRV"))
    assert linked.linked_to == "M04"


async def test_a_reply_naming_two_cases_finds_both_and_an_unknown_sender_none() -> None:
    """M01 and M08 are two of Velatrix's cases (M08 is a duplicate PO): a
    reply naming both is on a thread holding both, and which one it answers
    is not the thread's to say (ticket 24)."""
    world = _world()
    await world.process_each(AN, ["M01", "M08"])
    m01 = (await _sample(world, "M01")).model_copy(update={"internet_message_id": "<m1@v.example>"})
    m08 = (await _sample(world, "M08")).model_copy(update={"internet_message_id": "<m8@v.example>"})
    links = ThreadLinks(world.store, _Listed([m01, m08]))
    vlx = await _customer(world, "VLX")

    both = _reply("an.trinh@velatrix.example", ("<m1@v.example>", "<m8@v.example>"))
    assert [c.linked_to for c in await links.cases(ALPHA, both, vlx)] == ["M01", "M08"]
    one = _reply("an.trinh@velatrix.example", ("<m8@v.example>",))
    (linked,) = await links.cases(ALPHA, one, vlx)
    assert linked.linked_to == "M08"
    assert await links.cases(ALPHA, one, None) == ()


async def test_another_tenants_log_is_never_read_for_a_thread() -> None:
    """The store answers per scope: the demo tenant's cases are not there for
    a reply processed in tenant beta, whatever it names, even from a mailbox
    that lists the same messages to every scope."""
    world = _world()
    await _correction_requested(world)
    m04 = await _sample(world, "M04")
    reply = _reply("hana.westbrook@norvanta.example", (str(m04.internet_message_id),))
    links = ThreadLinks(world.store, _Listed([m04], every_scope=True))
    norvanta = await _customer(world, "NRV")

    assert await links.cases(ALPHA, reply, norvanta) != ()
    assert await links.cases(BETA, reply, norvanta) == ()


# --------------------------------------------------------- the reading --


async def test_the_model_reads_the_reply_and_code_keeps_only_what_it_located() -> None:
    model = _says("accepts", ACCEPT, "We accept everything you said earlier.")
    world = _world(model)
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.reply is not None
    reading = disposition.reply.reading
    assert reading is not None and reading.kinds == ("accepts",)
    assert [q.text for q in reading.intents[0].quotes] == [ACCEPT]
    assert (reading.prompt, reading.rules) == (str(REPLY_INTENT), "sales_order_rules@1.5.2")
    ((_, run, inputs),) = [c for c in model.calls if c[0] == REPLY_INTENT]
    assert run.tenant_id == ALPHA.tenant_id.value and run.worker_id == "sales-dw1"
    # The quoted older message was cut before the call, and the context is
    # code's words: who wrote it, and what Sales last asked.
    assert "infusion pump" not in inputs["body"]
    assert inputs["context"].startswith("The customer wrote this message")
    assert "QRL-RFQ-2609-03" in inputs["context"] and "accept" in inputs["context"]
    view = await world.services.quotes.get(AN.context(), case_id)
    (reply,) = view.replies
    assert (reply.message_id, reply.proposal) == ("M41", "settle_spec")
    assert [(i.intent, i.quotes) for i in reply.intents] == [("accepts", [ACCEPT])]


async def test_a_reading_with_no_located_quote_is_unclear_and_proposes_nothing() -> None:
    world = _world(_says("accepts", "We accept the price of 0 USD."))
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.reply is not None and disposition.reply.reading is not None
    (unclear,) = disposition.reply.reading.intents
    assert (unclear.intent, unclear.quotes) == ("unclear", ())
    (reply,) = (await world.services.quotes.get(AN.context(), case_id)).replies
    assert reply.proposal is None


async def test_one_message_reads_as_several_intents_each_on_its_own_quote() -> None:
    """Ticket 26 acceptance 1: "We accept line 1, please push line 3 to
    25/11" is an acceptance and a change, each standing on its sentence."""
    body = "We accept line 1, please push line 3 to 25/11."
    model = _saying(
        ("accepts", ("We accept line 1",)), ("requests_change", ("please push line 3 to 25/11",))
    )
    message = _reply("hana.westbrook@norvanta.example", (), body=body)

    reading = await ReplyReader(model).read(
        newest_part(message),
        author="customer",
        about="Sales is handling the customer's purchase order X.",
        rules_version="sales_order_rules@1.5.2",
        run=RUN,
    )

    assert [(i.intent, [q.text for q in i.quotes]) for i in reading.intents] == [
        ("accepts", ["We accept line 1"]),
        ("requests_change", ["please push line 3 to 25/11"]),
    ]


async def test_the_proposal_is_the_newest_replys_and_only_where_the_status_allows() -> None:
    world = _world(_says("accepts", ACCEPT))
    await world.process_each(AN, ["M09"])
    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()
    case_id = disposition.case_id
    assert case_id is not None

    (reply,) = (await world.services.quotes.get(AN.context(), case_id)).replies

    # The request is still `received`: settling a spec is no step from there.
    assert ([i.intent for i in reply.intents], reply.proposal) == (["accepts"], None)


async def test_with_the_switch_off_the_reply_is_attached_and_no_model_is_asked(
    tmp_path: Path,
) -> None:
    model = Recorded(failure=AssertionError("asked with the step off"))
    world = _world(model, _platform_rules_sample(tmp_path))
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert (disposition.case_id, disposition.reply is not None) == (case_id, True)
    assert disposition.reply is not None and disposition.reply.reading is None
    assert not [c for c in model.calls if c[0] == REPLY_INTENT]


async def test_the_model_down_leaves_the_reply_on_its_case_with_no_proposal() -> None:
    world = _world(Recorded(failure=ModelUnavailableError("InfrastructureError")))
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.kind == "attached_to_case" and disposition.case_id == case_id
    assert disposition.reply is not None and disposition.reply.reading is not None
    assert disposition.reply.reading.outcome == "unavailable"
    (reply,) = (await world.services.quotes.get(AN.context(), case_id)).replies
    assert (reply.outcome, reply.proposal) == ("unavailable", None)


async def test_a_spent_budget_stops_the_run_rather_than_reading_as_unavailable() -> None:
    world = _world(Recorded(failure=BudgetExceededError("run reached its ceiling")))
    await _spec_discussion(world)

    with pytest.raises(BudgetExceededError):
        await world.process_each(AN, ["M41"])
    assert world.store.state(ALPHA).messages.get("M41") is None


# ------------------------------------------ keeping the PO disposes nothing --


async def test_keeping_the_po_as_it_is_resumes_review_and_disposes_no_finding() -> None:
    world = _world(_says("rejects", KEEP))
    case_id = await _correction_requested(world)

    await world.process_each(AN, ["M42"])
    (reply,) = (await world.services.orders.get(AN.context(), case_id)).replies
    assert ([i.intent for i in reply.intents], reply.proposal) == (["rejects"], "resume_review")
    await world.services.order_commands.resume_review(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    case = world.order(case_id)
    assert case.status is OrderStatus.IN_REVIEW
    asked = {f.key for f in case.findings if f.disposition.kind is FindingDisposition.ASK_CUSTOMER}
    assert asked == {"price_mismatch:2", "code_unmapped:3"}
    # Each is still Sales' to decide: preparing is refused while one is asked.
    await world.open_sources(AN, case_id)
    with pytest.raises(ConflictError) as refused:
        await world.services.order_commands.prepare(
            AN.context(), case_id, case_version=case.case_version
        )
    assert set(cast(list[str], refused.value.details["ask_customer"])) == asked
    # Once resumed, the reply proposes nothing more.
    (reply,) = (await world.services.orders.get(AN.context(), case_id)).replies
    assert reply.proposal is None


async def test_review_resumes_only_from_a_correction_request() -> None:
    world = _world()
    ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
    assert disposition.case_id is not None

    with pytest.raises(ConflictError):
        await world.services.order_commands.resume_review(
            AN.context(),
            disposition.case_id,
            case_version=world.order(disposition.case_id).case_version,
        )


# ------------------------------------------------------------- the rules --


def test_a_quote_is_kept_only_once_in_the_newest_part() -> None:
    part = "Re: spec\n\nWe accept. We accept the spec. Thanks."

    found = located_quotes(part, ("We accept the spec.", "We accept", "From the older mail"))

    assert [q.text for q in found] == ["We accept the spec."]


def test_an_intent_without_a_located_quote_becomes_unclear() -> None:
    """Ticket 26 acceptance 2, and the guard's edges: an intent given twice
    is kept once, two unlocated ones are one ``unclear``, none is
    ``unclear``."""
    part = "Re: order\n\nWe accept line 1. Thanks."

    def kept(*given: tuple[str, list[str]]) -> list[tuple[str, int]]:
        answer = ModelThreadIntents.model_validate(
            {"intents": [{"intent": i, "quote_spans": q} for i, q in given]}
        )
        return [(i.intent, len(i.quotes)) for i in verified_intents(part, answer)]

    assert kept(("accepts", ["We accept line 1."])) == [("accepts", 1)]
    assert kept(("requests_change", ["Push line 3."])) == [("unclear", 0)]
    assert kept(("accepts", ["We accept line 1."]), ("cancels", ["Cancel it."])) == [
        ("accepts", 1),
        ("unclear", 0),
    ]
    assert kept(("asks", ["Why?"]), ("cancels", ["Cancel it."])) == [("unclear", 0)]
    assert kept(("accepts", ["We accept line 1."]), ("accepts", ["Thanks."])) == [("accepts", 2)]
    assert kept() == [("unclear", 0)]


def test_a_reading_that_names_an_intent_without_a_quote_is_refused() -> None:
    stamp = {
        "prompt": "sales.reply_intent@2.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.5.2",
    }
    ReplyReading.model_validate({**stamp, "outcome": "read", "intents": [{"intent": "unclear"}]})
    with pytest.raises(ValidationError):
        ReplyReading.model_validate(
            {**stamp, "outcome": "read", "intents": [{"intent": "accepts"}]}
        )
    with pytest.raises(ValidationError):
        ReplyReading.model_validate({**stamp, "outcome": "read", "intents": []})
    with pytest.raises(ValidationError):
        ReplyReading.model_validate(
            {**stamp, "outcome": "unavailable", "intents": [{"intent": "unclear"}]}
        )


def test_every_proposal_is_an_existing_step_from_the_status_it_starts_in() -> None:
    assert proposed_step("customer", "quote", "design_replied", _read("accepts")) is None
    assert proposed_step("customer", "quote", "spec_discussion", _read("requests_change")) is None
    assert proposed_step("customer", "quote", "spec_discussion", _read("unclear")) is None
    assert proposed_step("customer", "order", "in_review", _read("rejects")) is None
    assert proposed_step("customer", "order", "correction_requested", None) is None
    # The same words from Sales propose nothing a customer's would, and the
    # other way round.
    assert proposed_step("sales", "quote", "spec_discussion", _read("accepts")) is None
    assert proposed_step("customer", "order", "in_review", _read("asks")) is None
    assert proposed_step("sales", "order", "in_review", _read("asks")) == "request_correction"
    statuses = {"quote": {s.value for s in QuoteStatus}, "order": {s.value for s in OrderStatus}}
    for (_, kind, status, _), step in INTENT_STEPS.items():
        assert status in statuses[kind], step


def test_intents_pointing_at_two_steps_propose_neither() -> None:
    """Only one step can be taken from a status; which one is a person's."""
    both = _read("accepts", "rejects")

    assert proposed_step("customer", "quote", "spec_discussion", both) is None
    # Two intents pointing at the same step propose it once.
    same = _read("accepts", "rejects")
    assert proposed_step("customer", "order", "correction_requested", same) == "resume_review"
    # An intent with no row beside one with a row: the row's step.
    mixed = _read("accepts", "requests_change")
    assert proposed_step("customer", "quote", "spec_discussion", mixed) == "settle_spec"


def test_a_reply_is_a_disposition_on_a_case_only() -> None:
    with pytest.raises(ValidationError):
        MessageDisposition.model_validate(
            {
                "message_id": "X1",
                "kind": DispositionKind.ROUTED_TO_SALES,
                "reason": "other",
                "owner": "role:sales_pic",
                "reply": {"linked_to": "M04"},
            }
        )


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    long_question = "Sales asked the customer to correct their purchase order X, about: " + (
        ", ".join(f"price_mismatch (line {n})" for n in range(1, 30))
    )

    rendered = prompts.render(
        REPLY_INTENT.prompt_id,
        REPLY_INTENT.version,
        {"subject": "", "body": "", "context": reading_context("customer", long_question)},
        tenant_id=RUN.tenant_id,
    )

    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


async def test_a_long_body_is_cut_to_the_routes_room_before_it_is_sent() -> None:
    model = _says("asks", "Can you check?")
    message = _reply("hana.westbrook@norvanta.example", (), body="Can you check? " * 3000)

    await ReplyReader(model).read(
        newest_part(message),
        author="customer",
        about="Q",
        rules_version="sales_order_rules@1.5.2",
        run=RUN,
    )

    ((_, _, inputs),) = model.calls
    assert estimated_tokens(inputs["body"]) <= model.max_input_tokens - PROMPT_TOKENS


# ------------------------------------------------------------- helpers --


def _read(*intents: ThreadIntent) -> ReplyReading:
    return ReplyReading.model_validate(
        {
            "prompt": "sales.reply_intent@2.0.0",
            "model_profile": "onprem",
            "route": "structured_extraction",
            "rules": "sales_order_rules@1.5.2",
            "outcome": "read",
            "intents": [
                {
                    "intent": i,
                    "quotes": [] if i == "unclear" else [{"text": "x", "start": 0, "end": 1}],
                }
                for i in intents
            ],
        }
    )


def _reply(sender: str, references: tuple[str, ...], *, body: str = "Thanks.") -> InboundMessage:
    return InboundMessage(
        message_id="R1",
        sender=EmailAddress(address=sender),
        subject="Re: our order",
        received_at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC),
        body_text=body,
        references=references,
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


class _Listed:
    """A mailbox threading ``messages`` (stored in that order) to the demo
    scope, or to every scope as a misconfigured adapter would
    (``every_scope``)."""

    def __init__(self, messages: list[InboundMessage], *, every_scope: bool = False) -> None:
        self.threads, self.every_scope = ThreadIndex(messages), every_scope

    async def get_message(self, scope: SalesScope, message_id: str) -> InboundMessage | None:
        raise NotImplementedError("not exercised by the reply tests")

    async def thread_messages(
        self, scope: SalesScope, message: InboundMessage
    ) -> list[InboundMessage]:
        return self.threads.thread_of(message) if self.every_scope or scope == ALPHA else []


async def _sample(world: World, message_id: str) -> InboundMessage:
    message = await world.inbox.get_message(ALPHA, message_id)
    assert message is not None
    return message


async def _customer(world: World, code: str) -> Customer:
    customer = (await world.catalog.customer_by_code(ALPHA, code)).data
    assert customer is not None
    return customer


def _platform_rules_sample(tmp: Path) -> SampleSet:
    """The sample set with no tenant rules of its own: the platform's, every
    model step off."""
    shutil.copytree(DATA_DIR, tmp / "data", ignore=shutil.ignore_patterns("policies"))
    return SampleSet(tmp / "data", ATTACHMENTS_DIR)
