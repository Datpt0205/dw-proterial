"""A customer's reply in a case's thread: linked by its headers, read by a
model where the tenant turns it on, and never applied without Sales
(ticket 32, dw_sales ADR 0005).

Over the in-memory world (`dw_sales.evals.world`), the services the API
serves, with a scripted model (`Recorded`): which case a reply joins and which
it never joins, what code keeps of a reading, the step it proposes and where,
and that keeping the PO as it is disposes no finding. The live model's
accuracy is the eval lane's (`sales_reply@1.0.0`).
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
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import ConflictError
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.ports import SalesScope
from dw_sales.application.reply_intent import PROMPT_TOKENS, REPLY_INTENT, ReplyReader
from dw_sales.application.threads import ThreadedCase, ThreadLinks
from dw_sales.domain.catalog import Customer
from dw_sales.domain.dispositions import CaseKind, DispositionKind, MessageDisposition
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.domain.orders import DispositionKind as FindingDisposition
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.domain.reply_intent import (
    REPLY_STEPS,
    ReplyKind,
    ReplyReading,
    located_quotes,
    proposed_step,
    verified_kind,
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


def _says(kind: ReplyKind, *quotes: str) -> Recorded:
    return Recorded(raw={"quote_spans": list(quotes), "kind": kind})


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

    assert await links.linked_case(ALPHA, forged, await _customer(world, "QRL")) is None
    linked = await links.linked_case(ALPHA, own, await _customer(world, "NRV"))
    assert linked is not None and linked.linked_to == "M04"


async def test_a_reply_naming_two_cases_or_from_an_unknown_sender_links_nothing() -> None:
    """M01 and M08 are two of Velatrix's cases (M08 is a duplicate PO): a
    reply naming both points at neither."""
    world = _world()
    await world.process_each(AN, ["M01", "M08"])
    m01 = (await _sample(world, "M01")).model_copy(update={"internet_message_id": "<m1@v.example>"})
    m08 = (await _sample(world, "M08")).model_copy(update={"internet_message_id": "<m8@v.example>"})
    links = ThreadLinks(world.store, _Listed([m01, m08]))
    vlx = await _customer(world, "VLX")

    both = _reply("an.trinh@velatrix.example", ("<m1@v.example>", "<m8@v.example>"))
    assert await links.linked_case(ALPHA, both, vlx) is None
    one = _reply("an.trinh@velatrix.example", ("<m8@v.example>",))
    linked = await links.linked_case(ALPHA, one, vlx)
    assert linked is not None and linked.linked_to == "M08"
    assert await links.linked_case(ALPHA, one, None) is None


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

    assert await links.linked_case(ALPHA, reply, norvanta) is not None
    assert await links.linked_case(BETA, reply, norvanta) is None


# --------------------------------------------------------- the reading --


async def test_the_model_reads_the_reply_and_code_keeps_only_what_it_located() -> None:
    model = _says("accepts_spec", ACCEPT, "We accept everything you said earlier.")
    world = _world(model)
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.reply is not None
    reading = disposition.reply.reading
    assert reading is not None and reading.kind == "accepts_spec"
    assert [q.text for q in reading.quotes] == [ACCEPT]
    assert (reading.prompt, reading.rules) == (str(REPLY_INTENT), "sales_order_rules@1.5.1")
    ((_, run, inputs),) = [c for c in model.calls if c[0] == REPLY_INTENT]
    assert run.tenant_id == ALPHA.tenant_id.value and run.worker_id == "sales-dw1"
    # The quoted older message was cut before the call, and the case's
    # question is code's words.
    assert "infusion pump" not in inputs["body"]
    assert "QRL-RFQ-2609-03" in inputs["question"] and "accept" in inputs["question"]
    view = await world.services.quotes.get(AN.context(), case_id)
    (reply,) = view.replies
    assert (reply.message_id, reply.kind, reply.proposal) == ("M41", "accepts_spec", "settle_spec")
    assert reply.quotes == [ACCEPT]


async def test_a_reading_with_no_located_quote_is_unclear_and_proposes_nothing() -> None:
    world = _world(_says("accepts_spec", "We accept the price of 0 USD."))
    case_id = await _spec_discussion(world)

    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()

    assert disposition.reply is not None and disposition.reply.reading is not None
    assert (disposition.reply.reading.kind, disposition.reply.reading.quotes) == ("unclear", ())
    (reply,) = (await world.services.quotes.get(AN.context(), case_id)).replies
    assert reply.proposal is None


async def test_the_proposal_is_the_newest_replys_and_only_where_the_status_allows() -> None:
    world = _world(_says("accepts_spec", ACCEPT))
    await world.process_each(AN, ["M09"])
    ((disposition, _),) = (await world.process_each(AN, ["M41"])).values()
    case_id = disposition.case_id
    assert case_id is not None

    (reply,) = (await world.services.quotes.get(AN.context(), case_id)).replies

    # The request is still `received`: settling a spec is no step from there.
    assert (reply.kind, reply.proposal) == ("accepts_spec", None)


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
    world = _world(_says("keeps_po_as_is", KEEP))
    case_id = await _correction_requested(world)

    await world.process_each(AN, ["M42"])
    (reply,) = (await world.services.orders.get(AN.context(), case_id)).replies
    assert (reply.kind, reply.proposal) == ("keeps_po_as_is", "resume_review")
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
    assert verified_kind("accepts_spec", ()) == "unclear"
    assert verified_kind("accepts_spec", found) == "accepts_spec"


def test_a_reading_that_names_a_kind_without_a_quote_is_refused() -> None:
    stamp = {
        "prompt": "sales.reply_intent@1.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.5.1",
    }
    ReplyReading.model_validate({**stamp, "outcome": "read", "kind": "unclear"})
    with pytest.raises(ValidationError):
        ReplyReading.model_validate({**stamp, "outcome": "read", "kind": "accepts_spec"})


def test_every_proposal_is_an_existing_step_from_the_status_it_starts_in() -> None:
    assert proposed_step("quote", "design_replied", _read("accepts_spec")) is None
    assert proposed_step("quote", "spec_discussion", _read("counter_proposal")) is None
    assert proposed_step("quote", "spec_discussion", _read("unclear")) is None
    assert proposed_step("order", "in_review", _read("keeps_po_as_is")) is None
    assert proposed_step("order", "correction_requested", None) is None
    statuses = {"quote": {s.value for s in QuoteStatus}, "order": {s.value for s in OrderStatus}}
    for (kind, status, _), step in REPLY_STEPS.items():
        assert status in statuses[kind], step


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
        {"subject": "", "body": "", "question": long_question},
        tenant_id=RUN.tenant_id,
    )

    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


async def test_a_long_body_is_cut_to_the_routes_room_before_it_is_sent() -> None:
    model = _says("question", "Can you check?")
    message = _reply("hana.westbrook@norvanta.example", (), body="Can you check? " * 3000)
    thread = ThreadedCase(CaseKind.ORDER, uuid.UUID(int=1), "NRV", "in_review", "M04", "Q")

    await ReplyReader(model).read(
        newest_part(message), thread, rules_version="sales_order_rules@1.5.1", run=RUN
    )

    ((_, _, inputs),) = model.calls
    assert estimated_tokens(inputs["body"]) <= model.max_input_tokens - PROMPT_TOKENS


# ------------------------------------------------------------- helpers --


def _read(kind: ReplyKind) -> ReplyReading:
    quotes = () if kind == "unclear" else ({"text": "x", "start": 0, "end": 1},)
    return ReplyReading.model_validate(
        {
            "prompt": "sales.reply_intent@1.0.0",
            "model_profile": "onprem",
            "route": "structured_extraction",
            "rules": "sales_order_rules@1.5.1",
            "outcome": "read",
            "kind": kind,
            "quotes": quotes,
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
    """A mailbox listing ``messages`` to the demo scope, or to every scope as
    a misconfigured adapter would (``every_scope``)."""

    def __init__(self, messages: list[InboundMessage], *, every_scope: bool = False) -> None:
        self.messages, self.every_scope = messages, every_scope

    async def list_messages(self, scope: SalesScope) -> list[InboundMessage]:
        return self.messages if self.every_scope or scope == ALPHA else []


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
