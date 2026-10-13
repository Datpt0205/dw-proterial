"""A model reads what a message no reader accepted is about; code routes it.

Ticket 31, dw_sales ADR 0005 (the rules: `domain.message_intent`). Asked only
for a message whose attachments no reader accepted, where the tenant's rules
turn it on and a DW1 run is processing. `IntentReader.read` sends the subject
and the newest body part (`mail_parts.newest_part`, history cut by structure)
under prompt `sales.message_intent`, and returns what code accepts:

- the kind, from the closed set, which `order_intake.INTENT_ROUTES` maps to
  where the message goes; the model never names a route, an owner or a
  customer;
- the numbers it names that code finds in the newest part and that resolve
  exactly and uniquely against the sender's own customer's order cases, ERP
  orders or open YCBGs (`resolve`); a number of another customer, or of
  another tenant's records, resolves to nothing and is dropped;
- None when there is no usable answer (the model down, too slow, or outside
  the schema). A budget or quota refusal is not that: it propagates, and the
  run stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dw_agent_runtime.contracts import RunContext
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.order_ports import OrderCaseLookupPort
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.mail_parts import MessagePart
from dw_sales.domain.message_intent import (
    IntentKind,
    IntentReading,
    ModelMessageIntent,
    ResolvedReference,
    located_numbers,
)

# The prompt the intent is read with. Its file is
# `configs/prompts/sales/message_intent@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
MESSAGE_INTENT: Final = PromptRef("sales.message_intent", "1.0.0")
# A kind, a language and up to five short spans: about 60 tokens measured.
_OUTPUT_TOKENS: Final = 200
# What the prompt itself costs, held above its rendered size by a test, so
# the body is cut where the route's bound says and not later.
PROMPT_TOKENS: Final = 1200


@dataclass(frozen=True, slots=True)
class IntentRead:
    """A reading code accepted: the kind, the language and the references."""

    kind: IntentKind
    reading: IntentReading


@dataclass(frozen=True)
class IntentReader:
    """Reads a message's intent through a model and resolves what it names."""

    model: InterpretationPort
    catalog: SalesCatalogPort
    cases: OrderCaseLookupPort

    async def read(
        self,
        scope: SalesScope,
        part: MessagePart,
        customer: Customer | None,
        *,
        rules_version: str,
        run: RunContext,
    ) -> IntentRead | None:
        """The message's intent as code accepts it, or None for no usable answer."""
        inputs = {"subject": part.subject, "body": self._bounded(part.body)}
        try:
            answer = await self.model.interpret(
                MESSAGE_INTENT,
                inputs,
                ModelMessageIntent,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return None
        numbers = located_numbers(part.text, answer.referenced_number_spans)
        references = await self.resolve(scope, customer, numbers)
        return IntentRead(
            kind=answer.kind,
            reading=IntentReading(
                prompt=str(MESSAGE_INTENT),
                model_profile=self.model.model_profile,
                route=self.model.route,
                rules=rules_version,
                outcome="read",
                kind=answer.kind,
                language=answer.language,
                references=references,
            ),
        )

    def unavailable(self, rules_version: str) -> IntentReading:
        """The stamp of a message routed because no usable answer came."""
        return IntentReading(
            prompt=str(MESSAGE_INTENT),
            model_profile=self.model.model_profile,
            route=self.model.route,
            rules=rules_version,
            outcome="unavailable",
        )

    async def resolve(
        self, scope: SalesScope, customer: Customer | None, numbers: tuple[str, ...]
    ) -> tuple[ResolvedReference, ...]:
        """Each number that is exactly one of the sender's customer's records:
        a PO (an order case or an ERP order under that PO number) or an open
        YCBG (by its own number or the RFQ number it was raised for). A number
        that is both, or several YCBGs, or nothing, resolves to nothing. With
        no customer (a sender on no customer's domain) nothing resolves."""
        if customer is None:
            return ()
        ycbgs = (await self.catalog.open_ycbg(scope)).data
        resolved: list[ResolvedReference] = []
        for number in numbers:
            cases = await self.cases.cases_for_po(scope, customer.code, number)
            orders = (await self.catalog.orders_for_po(scope, customer.code, number)).data
            requests = [
                y
                for y in ycbgs
                if y.customer_code == customer.code and number in (y.ycbg_no, y.rfq_no)
            ]
            is_po = bool(cases) or bool(orders)
            if is_po and not requests:
                live = [case for case in cases if case.superseded_by_case is None]
                resolved.append(
                    ResolvedReference(
                        number=number,
                        record="purchase_order",
                        order_case_id=live[0].case_id if len(live) == 1 else None,
                    )
                )
            elif len(requests) == 1 and not is_po:
                resolved.append(ResolvedReference(number=number, record="quote_request"))
        return tuple(resolved)

    def _bounded(self, body: str) -> str:
        """The body cut to what fits the route with the prompt beside it: the
        kind of a message is in its first lines, and the rest is not sent."""
        room = self.model.max_input_tokens - PROMPT_TOKENS
        if estimated_tokens(body) <= room:
            return body
        cut = body
        while cut and estimated_tokens(cut) > room:
            cut = cut[: len(cut) * 3 // 4]
        return cut
