"""The per-run ceiling, which was configured and unenforced until it was not."""

from __future__ import annotations

import uuid

import pytest

from dw_agent_runtime.model.budget import (
    BudgetExceededError,
    RunBudgetLedger,
    route_cost,
)
from dw_agent_runtime.model.profiles import ModelBudgets, ModelRoute

pytestmark = pytest.mark.unit

_PRICED = ModelRoute(
    provider="openai_responses",
    model="gpt-5.6-luna",
    price_per_million_input=0.20,
    price_per_million_output=1.20,
)
_UNPRICED = ModelRoute(provider="mock", model="mock-structured")
_TIGHT = ModelBudgets(max_input_tokens_per_run=10_000, max_cost_usd_per_run=0.01)


class TestRouteCost:
    def test_a_priced_route_costs_what_it_declares(self) -> None:
        # 1M input at $0.20 and 1M output at $1.20.
        assert route_cost(_PRICED, 1_000_000, 1_000_000) == pytest.approx(1.40)

    def test_a_realistic_extraction_call_is_fractions_of_a_cent(self) -> None:
        assert route_cost(_PRICED, 6242, 236) == pytest.approx(0.00153, abs=1e-5)

    def test_an_unpriced_route_contributes_nothing(self) -> None:
        # Honest rather than convenient: such a run is bounded by the token
        # ceiling, and pretending a price would make the cost figure fiction.
        assert route_cost(_UNPRICED, 1_000_000, 1_000_000) == 0.0


class TestLedger:
    def test_a_fresh_run_may_always_make_its_first_call(self) -> None:
        RunBudgetLedger().check(uuid.uuid4(), _TIGHT, task="first")

    def test_spending_accumulates_across_calls(self) -> None:
        ledger, run = RunBudgetLedger(), uuid.uuid4()
        ledger.record(run, input_tokens=100, output_tokens=10, cost_usd=0.001)
        spend = ledger.record(run, input_tokens=100, output_tokens=10, cost_usd=0.001)
        assert (spend.input_tokens, spend.calls) == (200, 2)

    def test_the_token_ceiling_stops_the_next_call(self) -> None:
        ledger, run = RunBudgetLedger(), uuid.uuid4()
        ledger.record(run, input_tokens=10_000, output_tokens=0, cost_usd=0.0)
        with pytest.raises(BudgetExceededError, match="input-token ceiling"):
            ledger.check(run, _TIGHT, task="next")

    def test_the_cost_ceiling_stops_the_next_call(self) -> None:
        ledger, run = RunBudgetLedger(), uuid.uuid4()
        ledger.record(run, input_tokens=1, output_tokens=1, cost_usd=0.01)
        with pytest.raises(BudgetExceededError, match="cost ceiling"):
            ledger.check(run, _TIGHT, task="next")

    def test_the_error_says_which_run_and_how_many_calls(self) -> None:
        # A ceiling that fires without saying what hit it turns a loop into a
        # mystery, which is the thing the ceiling exists to make visible.
        ledger, run = RunBudgetLedger(), uuid.uuid4()
        for _ in range(7):
            ledger.record(run, input_tokens=2_000, output_tokens=0, cost_usd=0.0)
        with pytest.raises(BudgetExceededError) as caught:
            ledger.check(run, _TIGHT, task="section_extract:financials:r2")
        details = caught.value.details
        assert details["run_id"] == str(run)
        assert details["calls"] == "7"
        assert details["task"] == "section_extract:financials:r2"

    def test_one_run_reaching_its_ceiling_does_not_stop_another(self) -> None:
        ledger, spent, fresh = RunBudgetLedger(), uuid.uuid4(), uuid.uuid4()
        ledger.record(spent, input_tokens=10_000, output_tokens=0, cost_usd=0.0)
        ledger.check(fresh, _TIGHT, task="unrelated")

    def test_a_finished_run_is_forgotten_so_a_worker_does_not_accumulate_them(self) -> None:
        ledger, run = RunBudgetLedger(), uuid.uuid4()
        ledger.record(run, input_tokens=5, output_tokens=1, cost_usd=0.0)
        assert ledger.forget(run) is not None
        assert ledger.spend == {}
