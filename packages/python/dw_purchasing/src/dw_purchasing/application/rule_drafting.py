"""A purchasing rule changed in words: "hạn mức trưởng phòng lên 50 triệu".

The person who configures DW2 types what they want; the model answers with
changes (a path of the version in force and the value it should hold,
`purchasing.rule_change_in_words@1.0.0`); the platform's checks decide
whether a draft exists (`dw_platform.application.rule_words.apply_changes`:
a path the document has, under the part asked about, the type its field
holds, the whole document through the key's schema). Nothing is stored and
nothing applies: the draft comes back with the paths it changed and a
version number nobody has used, the settings page shows the difference in
words, and the person sends it through the one door every version takes
(`PurchasingRulesService.propose`), where a second person decides it.

Answered synchronously, as a person waits for it: a model that is down, or
an answer that does not parse, says so ("DW2 chưa đọc được lúc này"), never
a guessed change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import DomainError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import ContextScope
from dw_platform.application.rule_words import (
    MAX_REQUEST_CHARS,
    ModelRuleChanges,
    WordsApplied,
    apply_changes,
    focus_of,
    leaf_paths,
)
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import Worker
from dw_purchasing.application.rules import (
    SCHEMAS,
    SETTINGS_KEYS,
    PurchasingRuleBook,
    rule_key,
    unused_version,
)

RULE_CHANGE_IN_WORDS: Final = PromptRef("purchasing.rule_change_in_words", "1.0.0")
_PROMPT_TOKENS: Final = 1200
_OUTPUT_TOKENS: Final = 1500
NOT_NOW: Final = "DW2 chưa đọc được lúc này: thử lại sau, hoặc sửa trực tiếp trên biểu mẫu"
_FOCUS: Final = r"^[A-Za-z_][A-Za-z0-9_.]*$"


class WordsDraft(BaseModel):
    """What the settings page shows: the whole document changed, the paths
    the machine changed ("Máy đề xuất"), the version it would be, or the
    problems that refused it (codes and paths, never a word of the model's)."""

    model_config = ConfigDict(frozen=True)

    key: str
    base_ref: str
    document: dict[str, Any] | None
    changed: list[str]
    version: str | None
    problems: list[str]


@dataclass(frozen=True)
class RuleWordsDesk:
    gate: Gate
    book: PurchasingRuleBook
    model: InterpretationPort | None
    worker: Worker
    ids: IdGenerator

    async def draft(
        self, context: AccessContext, key: str, request: str, focus: str | None = None
    ) -> WordsDraft:
        await self.gate.require(
            context, PurchasingScopes.RULES_PROPOSE, resource_type="purchasing_rule_version"
        )
        rule = rule_key(key)
        if rule not in SETTINGS_KEYS:
            # The master data is a workbook's to change, not a sentence's.
            raise NotFoundError("no such rule key")
        words = request.strip()
        if not words:
            raise DomainError("hãy viết điều cần đổi", details={"rule": "request_empty"})
        if len(words) > MAX_REQUEST_CHARS:
            raise DomainError(
                f"yêu cầu dài hơn {MAX_REQUEST_CHARS} ký tự", details={"rule": "request_long"}
            )
        if self.model is None:
            raise InfrastructureError(NOT_NOW, details={"reason_code": "no_model"})
        scope = ContextScope(TenantId(context.tenant_id), WorkspaceId(context.workspace_id))
        current = (await self.book.current(scope, rule)).policy
        base = current.model_dump(mode="json", by_alias=True)
        try:
            part = focus_of(base, focus)
        except (KeyError, IndexError, ValueError):
            raise DomainError(
                "quy tắc không có phần được yêu cầu sửa", details={"rule": "focus"}
            ) from None
        # The person's words first: what a scripted model in the evals keys on.
        inputs = {
            "request": words,
            "rule_name": rule.value,
            "document": json.dumps(part, ensure_ascii=False, indent=1),
            "paths": "\n".join(leaf_paths(part)),
        }
        if estimated_tokens("".join(inputs.values())) > (
            self.model.max_input_tokens - _PROMPT_TOKENS
        ):
            raise DomainError(
                "phần cần sửa quá dài cho một lần đọc: chọn phần nhỏ hơn",
                details={"rule": "focus_too_long"},
            )
        run = caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker.worker_id,
            worker_version=self.worker.worker_version,
            trace="dw2-rule-words",
            subject_ref=f"purchasing_rule:{rule.value}",
        )
        try:
            answer = await self.model.interpret(
                RULE_CHANGE_IN_WORDS,
                inputs,
                ModelRuleChanges,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError as exc:
            raise InfrastructureError(NOT_NOW, details={"reason_code": "model"}) from exc
        applied = apply_changes(SCHEMAS[rule], base, answer, request=words, focus=focus)
        if not isinstance(applied, WordsApplied):
            return WordsDraft(
                key=rule.value,
                base_ref=current.ref,
                document=None,
                changed=[],
                version=None,
                problems=[str(p) for p in applied.problems],
            )
        version = await unused_version(self.book, scope, rule.value, base["policy_version"])
        document = {**applied.document, "policy_version": version}
        return WordsDraft(
            key=rule.value,
            base_ref=current.ref,
            document=document,
            changed=list(applied.changed),
            version=version,
            problems=[],
        )
