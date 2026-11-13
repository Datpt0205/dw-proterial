"""A refusal's constraint is the driver's typed field, never a word in its text
(audit 19).

Shaped as SQLAlchemy raises it over asyncpg: the DBAPI error SQLAlchemy wraps
has asyncpg's own exception as its cause, which carries `constraint_name`. The
integration suites of each repository that reads it (offboarding, workspaces,
decision codes, runs, RFQ mails, mail outcomes) drive the real driver.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from dw_platform.adapters.persistence.integrity import constraint_of

pytestmark = pytest.mark.unit


class _DriverError(Exception):
    def __init__(self, message: str, constraint_name: str | None) -> None:
        super().__init__(message)
        self.constraint_name = constraint_name


def _refused(message: str, constraint_name: str | None) -> IntegrityError:
    orig = Exception(message)
    orig.__cause__ = _DriverError(message, constraint_name)
    return IntegrityError("INSERT ...", {}, orig)


def test_the_typed_name_wins_over_a_name_the_text_quotes() -> None:
    # A detail that quotes another constraint's name (a slug, a value, a
    # longer name containing a shorter one) would match a substring search.
    refused = _refused(
        'duplicate key value violates unique constraint "uq_rfq_mails_case_id_supplier_code_active"'
        " DETAIL: Key (slug)=(uq_workspaces_tenant_slug) already exists.",
        "uq_rfq_mails_case_id_supplier_code_active",
    )

    assert constraint_of(refused) == "uq_rfq_mails_case_id_supplier_code_active"


def test_no_typed_name_is_none_whatever_the_text_says() -> None:
    assert constraint_of(_refused('violates "pk_mail_outcomes"', None)) is None
