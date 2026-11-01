"""purchasing permissions an admin grants

Revision ID: fcc0e57d0817
Revises: b60b5a0a4c91
Create Date: 2026-11-01 09:59:26.604365+00:00

Three questions that were Proterial's to answer become grants a tenant's
admin makes on the members page, the day they know (Đạt, 2026-11-01):

- **Who downloads the Bravo file**: its own scope `purchasing.po.download`,
  held by `purchasing_buyer` as before (no one loses it), and a permission
  set `purchasing_po_downloader` an admin adds to anyone else.
- **Who reads every request**: permission set `purchasing_request_reader`
  (`purchasing.request.read`), for a director who also wants the list, not
  only the request waiting on them.
- **Who decides a change of the purchasing rules**: permission set
  `purchasing_rules_approver` (`purchasing.rules.approve`), for a director
  in place of, or beside, the head. The settings page reads with it.
"""

from __future__ import annotations

import json

from alembic import op

revision = "fcc0e57d0817"
down_revision = "b60b5a0a4c91"
branch_labels = None
depends_on = None

_DOWNLOAD = "purchasing.po.download"
_SETS = (
    ("purchasing_po_downloader", "Tải file Bravo của đơn mua hàng", (_DOWNLOAD,)),
    ("purchasing_request_reader", "Xem mọi yêu cầu mua hàng", ("purchasing.request.read",)),
    ("purchasing_rules_approver", "Duyệt thay đổi quy tắc mua hàng", ("purchasing.rules.approve",)),
)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scopes(scopes: tuple[str, ...]) -> str:
    return _literal(json.dumps(list(scopes))) + "::jsonb"


def upgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || {_scopes((_DOWNLOAD,))}"
        " WHERE key = 'purchasing_buyer'"
    )
    for key, name, scopes in _SETS:
        op.execute(
            "INSERT INTO platform.permission_sets (key, name, scopes)"
            f" VALUES ({_literal(key)}, {_literal(name)}, {_scopes(scopes)})"
        )


def downgrade() -> None:
    keys = ", ".join(_literal(key) for key, _, _ in _SETS)
    op.execute(f"DELETE FROM platform.permission_sets WHERE key IN ({keys})")
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - {_literal(_DOWNLOAD)}"
        " WHERE key = 'purchasing_buyer'"
    )
