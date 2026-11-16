"""A customer's SalesOrder skill: how that customer's PO becomes Bravo's
SalesOrder file, in words (ticket 41, dw_sales ADR 0013 as amended under ADR
0014).

One skill per customer, ``salesorder-<customer code>`` (lower case), stored
as any skill is: a tenant's version is a row of `platform.rule_versions`
under ``sales_skill_salesorder_<code>`` (`skills.salesorder_key`), proposed by
whoever proposes rules and decided by the head on a `sales.skills` approval,
never by its proposer. The platform ships one generic skill
(``configs/skills/dw1-salesorder/salesorder/SKILL.md``, fictional worked
pairs only: the repository is public); a customer with no approved version
of its own is filled with it.

`PlatformSkills` is the platform layer a `skills.SkillBook` resolves over:
DW1's skills by key, and the generic SalesOrder skill under any customer's
key. It answers a customer's key and never lists one, so the skills a thread
turn is served and the skills page lists stay DW1's own; and the platform's
rule-version engine, guard and settlement hold a customer's versions with no
change, since each asks the book for the key's platform layer.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from dw_platform.application.rule_versions import RuleScope, RuleVersionLookupPort
from dw_sales.application.salesorder_fill import FillSkill
from dw_sales.application.skills import (
    Dw1Skills,
    SkillBook,
    SkillDocument,
    is_salesorder_key,
    salesorder_key,
)

__all__ = ["PlatformSkills", "customer_skill", "salesorder_skill_book"]


@dataclass(frozen=True)
class PlatformSkills(Mapping[str, SkillDocument]):
    """DW1's skills by key, and for every customer's SalesOrder key the
    generic SalesOrder skill under that key (module docstring)."""

    skills: Mapping[str, SkillDocument]
    salesorder: SkillDocument

    def __getitem__(self, key: str) -> SkillDocument:
        if key in self.skills:
            return self.skills[key]
        if is_salesorder_key(key):
            return self.salesorder.model_copy(update={"policy_id": key})
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.skills)

    def __len__(self) -> int:
        return len(self.skills)


def salesorder_skill_book(
    skills: Dw1Skills, stored: RuleVersionLookupPort, salesorder: SkillDocument
) -> SkillBook:
    """`skills.skill_book`'s book, whose platform layer also answers every
    customer's SalesOrder key with ``salesorder``, the generic skill."""
    return SkillBook(
        platform=PlatformSkills(dict(skills.skills), salesorder),
        stored=stored,
        schemas=dict.fromkeys(skills.skills, SkillDocument),
    )


async def customer_skill(book: SkillBook, scope: RuleScope, customer_code: str) -> FillSkill:
    """The customer's SalesOrder skill in force for ``scope``'s tenant: its
    approved version, else the platform's generic one; never another
    tenant's (`RuleBook.current`)."""
    document = (await book.current(scope, salesorder_key(customer_code))).policy
    assert isinstance(document, SkillDocument)
    return FillSkill(ref=document.ref, instructions=document.instructions)
