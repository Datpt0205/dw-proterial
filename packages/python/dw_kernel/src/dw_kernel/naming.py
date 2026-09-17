"""The one naming convention every database object in this repo is created under.

Lives in the kernel because four packages own tables — platform, agent runtime,
knowledge, memory — and a convention written out four times is four conventions
waiting to drift. It is a dict of format strings and imports nothing, so the
kernel stays stdlib-only; each package passes it to its own ``MetaData``.

Why it matters beyond tidiness: Postgres invents a name for any constraint you
do not name (``<table>_pkey``, ``<table>_<column>_fkey``), and a later migration
that wants to drop or alter one has to know that invented name. With a
convention the name is derivable from the table and the columns, so
``op.drop_constraint`` is something you can write correctly without first
querying the database.

``ix`` deliberately omits the table name's schema and takes the column list, so
a composite index reads as what it covers.
"""

from __future__ import annotations

from typing import Final

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

__all__ = ["NAMING_CONVENTION"]
