"""DW1's eval graders, keyed ``sales.<gate>``, for the eval runner's
composition root to hand to `dw_evals.runner.run_dataset` (see `graders`,
and `descriptions`, `intents`, `requests`, `replies`, `handoffs` and
`layouts` for the model steps of tickets 28, 31, 29, 32, 33 and 30,
`legacy` for ticket 27's converted and scanned POs, `corrections` for
ticket 15's header path, and `rule_drafts` for a layout drafted from a
company's template, `rule_words` for one changed in words)."""

from dw_sales.evals.corrections import GRADERS as CORRECTION_GRADERS
from dw_sales.evals.descriptions import GRADERS as DESCRIPTION_GRADERS
from dw_sales.evals.finding_explanations import GRADERS as EXPLANATION_GRADERS
from dw_sales.evals.graders import GRADERS as ORDER_GRADERS
from dw_sales.evals.handoffs import GRADERS as HANDOFF_GRADERS
from dw_sales.evals.intents import GRADERS as INTENT_GRADERS
from dw_sales.evals.layouts import GRADERS as LAYOUT_GRADERS
from dw_sales.evals.legacy import GRADERS as LEGACY_GRADERS
from dw_sales.evals.recorded import failing_without_live_answers
from dw_sales.evals.replies import GRADERS as REPLY_GRADERS
from dw_sales.evals.requests import GRADERS as REQUEST_GRADERS
from dw_sales.evals.rule_drafts import GRADERS as RULE_DRAFT_GRADERS
from dw_sales.evals.rule_words import GRADERS as RULE_WORDS_GRADERS
from dw_sales.evals.sender_customers import GRADERS as SENDER_GRADERS
from dw_sales.evals.thread_summaries import GRADERS as THREAD_GRADERS

# Every grader, failing a live case whose model gave no usable answer
# (`recorded.failing_without_live_answers`): one wrap here, so a grader
# added to any table is covered without remembering to.
GRADERS = {
    name: failing_without_live_answers(grader)
    for name, grader in {
        **ORDER_GRADERS,
        **CORRECTION_GRADERS,
        **DESCRIPTION_GRADERS,
        **INTENT_GRADERS,
        **REQUEST_GRADERS,
        **REPLY_GRADERS,
        **HANDOFF_GRADERS,
        **LAYOUT_GRADERS,
        **LEGACY_GRADERS,
        **RULE_DRAFT_GRADERS,
        **RULE_WORDS_GRADERS,
        **EXPLANATION_GRADERS,
        **SENDER_GRADERS,
        **THREAD_GRADERS,
    }.items()
}

__all__ = ["GRADERS"]
