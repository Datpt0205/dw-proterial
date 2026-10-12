# 26 — No customer data reaches a tracked file (G34)

Status: ready-for-agent
Blocked by: —
Category: enhancement

Split from ticket 12 on 2026-10-12.

## What

The repo is public and names Proterial and its procedure codes on purpose
(Đạt, 2026-10-05: keep it public, do not alias). What must never be tracked
is Proterial's data: real customer names, PIC names and emails, prices,
survey content. Today one test checks the mock fixtures for the word
"proterial" (`test_mock_scenarios.py`); nothing checks the rest of the tree.

## Acceptance

1. A script reads a deny-list from a path outside git (an env var naming it;
   absent locally → the check says it is skipped, loudly, and exits 0;
   absent in CI → exit non-zero) and scans every file `git ls-files` lists
   for each term, case-insensitive, Vietnamese diacritics normalised.
2. It runs in the pre-commit hook over staged files and in CI over the whole
   tree, with the deny-list supplied as a CI secret.
3. An allow-list in git for the deliberate names (Proterial, PRV, WIV-03-0xx)
   so they never need to be on the deny-list.
4. A test feeds the script a temporary deny-list and a temp file containing a
   term and asserts it fails; removing the scan turns it red.
5. `.gitignore` covers the places Proterial's documents land locally
   (`docs/design/`, `*.docx` under `docs/`), checked by the same script.

## Out of scope

- Rewriting git history (nothing found yet to rewrite).

## Sources (as of 2026-10-12)

- `dw_sales/tests/unit/test_mock_scenarios.py` (current fixture guard),
  `.claude/hooks/pre-commit-gate.sh`, `.github/workflows/ci.yml`,
  `sales.md` Open ("Public repo").

## Comments
