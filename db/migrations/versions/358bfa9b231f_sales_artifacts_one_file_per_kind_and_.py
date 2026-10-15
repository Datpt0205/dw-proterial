"""sales artifacts one file per kind and version

Revision ID: 358bfa9b231f
Revises: 2dd12f5b9c88
Create Date: 2026-10-15 03:21:29.226535+00:00

Sales ticket 06, open item: rendering a kind again at the same case version
answers what is stored, but two renders at once both found nothing stored and
both recorded their files. A case holds one file of each kind and content
type per version (a quotation is an xlsx and a PDF of one kind):

- **`uq_artifacts_order_case_id_case_version_kind_content_type`** and
  **`uq_artifacts_quote_case_id_case_version_kind_content_type`**, one per
  case column (the other is NULL, and NULLs never conflict). The repository
  inserts with ON CONFLICT DO NOTHING on these, so the render that commits
  second records nothing, removes the objects it stored, and answers the
  first one's files. Each also indexes its case column first, as the
  existing per-case indexes do.

Fails if a case already holds two files of one kind, content type and
version: nothing is deleted here, since an artifact is a record of what was
handed to someone. No deployment holds Sales data but the demo, which
`make demo-reset` rebuilds.
"""

from __future__ import annotations

from alembic import op

revision = "358bfa9b231f"
down_revision = "2dd12f5b9c88"
branch_labels = None
depends_on = None

_COLUMNS = "case_version, kind, content_type"


def upgrade() -> None:
    for case in ("order_case_id", "quote_case_id"):
        op.execute(
            "ALTER TABLE sales.artifacts"
            f" ADD CONSTRAINT uq_artifacts_{case}_case_version_kind_content_type"
            f" UNIQUE ({case}, {_COLUMNS})"
        )


def downgrade() -> None:
    for case in ("order_case_id", "quote_case_id"):
        op.execute(
            "ALTER TABLE sales.artifacts"
            f" DROP CONSTRAINT uq_artifacts_{case}_case_version_kind_content_type"
        )
