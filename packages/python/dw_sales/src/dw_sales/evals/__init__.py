"""DW1's eval graders, keyed ``sales.<gate>``, for the eval runner's
composition root to hand to `dw_evals.runner.run_dataset` (see `graders`,
and `descriptions`, `intents`, `requests`, `replies`, `handoffs` and
`layouts` for the model steps of tickets 28, 31, 29, 32, 33 and 30, and
`legacy` for ticket 27's converted and scanned POs)."""

from dw_sales.evals.descriptions import GRADERS as DESCRIPTION_GRADERS
from dw_sales.evals.graders import GRADERS as ORDER_GRADERS
from dw_sales.evals.handoffs import GRADERS as HANDOFF_GRADERS
from dw_sales.evals.intents import GRADERS as INTENT_GRADERS
from dw_sales.evals.layouts import GRADERS as LAYOUT_GRADERS
from dw_sales.evals.legacy import GRADERS as LEGACY_GRADERS
from dw_sales.evals.replies import GRADERS as REPLY_GRADERS
from dw_sales.evals.requests import GRADERS as REQUEST_GRADERS

GRADERS = {
    **ORDER_GRADERS,
    **DESCRIPTION_GRADERS,
    **INTENT_GRADERS,
    **REQUEST_GRADERS,
    **REPLY_GRADERS,
    **HANDOFF_GRADERS,
    **LAYOUT_GRADERS,
    **LEGACY_GRADERS,
}

__all__ = ["GRADERS"]
