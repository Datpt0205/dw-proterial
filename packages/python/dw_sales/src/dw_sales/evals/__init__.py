"""DW1's eval graders, keyed ``sales.<gate>``, for the eval runner's
composition root to hand to `dw_evals.runner.run_dataset` (see `graders`,
and `descriptions` for ticket 28's model step)."""

from dw_sales.evals.descriptions import GRADERS as DESCRIPTION_GRADERS
from dw_sales.evals.graders import GRADERS as ORDER_GRADERS

GRADERS = {**ORDER_GRADERS, **DESCRIPTION_GRADERS}

__all__ = ["GRADERS"]
