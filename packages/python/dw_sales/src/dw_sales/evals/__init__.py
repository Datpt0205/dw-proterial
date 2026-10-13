"""DW1's eval graders, keyed ``sales.<gate>``, for the eval runner's
composition root to hand to `dw_evals.runner.run_dataset` (see `graders`,
and `descriptions`, `intents` and `requests` for the model steps of tickets
28, 31 and 29)."""

from dw_sales.evals.descriptions import GRADERS as DESCRIPTION_GRADERS
from dw_sales.evals.graders import GRADERS as ORDER_GRADERS
from dw_sales.evals.intents import GRADERS as INTENT_GRADERS
from dw_sales.evals.requests import GRADERS as REQUEST_GRADERS

GRADERS = {**ORDER_GRADERS, **DESCRIPTION_GRADERS, **INTENT_GRADERS, **REQUEST_GRADERS}

__all__ = ["GRADERS"]
