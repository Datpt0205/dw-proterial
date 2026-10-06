"""DW1's eval graders, keyed ``sales.<gate>``, for the eval runner's
composition root to hand to `dw_evals.runner.run_dataset` (see `graders`)."""

from dw_sales.evals.graders import GRADERS

__all__ = ["GRADERS"]
