"""The prompt the case chat reads a person's sentence with (tickets 46, 56, 57).

Its own module so that `model_readiness.BARS`, which names the prompt each
step's live eval measures, reads it without importing the assistant and
everything the assistant composes.

The file is `configs/prompts/sales/question_intent@<version>.yaml`.
1.1.0 (ticket 46): the three steps of a case a person may ask for.
1.2.0 (ticket 56): a decision on one of the case's open flags (FLAGS).
1.3.0 (ticket 56): an SO line's confirmed date or quantity to write into Bravo.
1.4.0 (tester pass, 2026-11-22): a decision's flag and reason may come from the
person's own earlier turns, as staff talk around the point.
"""

from __future__ import annotations

from typing import Final

from dw_agent_runtime.model.interpretation import PromptRef

QUESTION_INTENT: Final = PromptRef("sales.question_intent", "1.5.0")
