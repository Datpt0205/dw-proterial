# 26 — No customer data reaches a tracked file (G34)

Status: done (2026-10-12; committed in dd5ef1d; adversarially reviewed and
fixed the same day, see "Review"). Owed by a person: the
`PUBLIC_REPO_DENYLIST` repository secret; until it exists the CI step fails,
as acceptance 1 asks
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

- Decided by the agent (Đạt away), 2026-10-12: the allow-list is
  `scripts/public_repo_allowlist.txt`, one regex per line matched WHOLE
  against a deny-list entry (lower-cased, diacritics removed). An entry it
  matches is a deliberate public name and is not searched for, so a deny-list
  built from Proterial's documents can keep "Proterial", "PRV" or
  "WIV-03-012" without failing every file. It does not mask text: a deny term
  that merely contains an allowed name is still searched for whole.
- Decided by the agent (Đạt away), 2026-10-12: a term matches as a
  SUBSTRING, not a whole word, and whitespace inside a term matches any run
  of whitespace including a line break. Fail closed: a name glued to the
  next spreadsheet cell or split across Word runs is still that name; the
  cost is that a deny-list entry must be specific (a full name, an email, a
  price with its separators).
- Decided by the agent (Đạt away), 2026-10-12: the output never contains a
  term, only `path:line: deny-list line N`. The CI log of a public repo is
  public, and GitHub's masking of a multi-line secret is not something to
  rely on.
- Decided by the agent (Đạt away), 2026-10-12: tracked `.xlsx`/`.docx` (any
  zip) are read member by member with XML tags removed and character
  references decoded, and PDFs through pypdf's text layer: 27 spreadsheets
  and 2 PDFs are tracked, and a byte scan sees nothing in any of them
  (failure-modes #0). A file that cannot be opened is a finding.
- Decided by the agent (Đạt away), 2026-10-12: a deny-list that is empty,
  holds only allow-listed names, cannot be read, or sits inside the
  checkout fails the check everywhere, not only in CI. An empty CI secret
  therefore fails too.
- Decided by the agent (Đạt away), 2026-10-12: "the pre-commit hook" is
  both hooks. `.pre-commit-config.yaml` gains a local `public-repo-guard`
  hook (the git hook, which sees exactly what is staged), and
  `.claude/hooks/pre-commit-gate.sh` runs the same `--staged` scan after
  the invariants: this checkout has no git hook installed (`make bootstrap`
  installs it with a `-`), so for an agent's commit the gate is the one that
  runs. The gate sees the index BEFORE the command runs, so a command that
  stages files and then commits in one line is the git hook's to catch.
- Decided by the agent (Đạt away), 2026-10-12, in review: a file's NAME is
  scanned as well as its content (`PO_Nguyen_Van_A.xlsx` publishes the name),
  and whitespace inside a term also matches underscores, so a term written
  with spaces finds a file named with `_`.
- Decided by the agent (Đạt away), 2026-10-12, in review: a PDF with no text
  layer at all is printed as `NOT CHECKED` and does not fail. The mock M16 is
  a scan on purpose (`generate_attachments.py`'s `_scanned_pdf`, whose data is
  in scanned files), and failing it would make the guard fail on the tree it
  guards. A legacy binary Office file (.xls/.doc, an OLE file) IS a finding:
  none is tracked, and DW1 refuses one as input too.

## Review (2026-10-12, adversarial reviewer)

Fixed, each with a test that went red when the fix was reverted (12 mutations
of the script, all red, restored and checked with `cmp`):

- The skip was not loud where it runs. pre-commit hides a passing hook's
  output, and a skip passes, so the "customer data was NOT checked" banner never
  showed in the git hook (shown in a throwaway repo: present with
  `verbose: true`, absent without it). The hook now has `verbose: true`. The
  Claude commit gate also swallowed it (it captures the output and prints it
  only on failure); it now returns the skip as a `systemMessage` to the person,
  with a hook test that goes red when the line is removed (80 hook cases).
- failure-modes #0, what the scan could not see: a workbook embedded in a Word
  document (a zip inside a zip, read as compressed bytes); `\uXXXX` escapes
  (JSON written with Python's default `ensure_ascii`, a string literal in
  code); character references outside Office XML (`&#7891;` in HTML); a
  UTF-16 text file (Excel's "Unicode text" export); a file's name; and a
  legacy .xls/.doc, which passed as unreadable bytes. All are read or reported
  now. The banner said "CI runs it on every push"; CI runs on pull requests
  and main, and only AFTER the push has published the branch, which is what it
  now says.
- The security note's remedy was wrong. Running `main`'s copy of the script
  would not protect the secret: a same-repository pull request can change the
  workflow file itself, and `pull_request` runs it with secrets. Anyone with
  write access can read any repository secret that way; that is GitHub's
  trust model, not this script's. Narrowing it needs a GitHub Environment with
  required reviewers holding the secret, which is a setting for a person, not
  code. Fork pull requests get no secret, so the step fails there (closed).

Not seen, and said so in the script's docstring (open, not fixed here):

- Vietnamese typed in a legacy 8-bit font (TCVN3/VNI) reads as other letters
  until ticket 20's detection becomes conversion (ADR 0010 decision 3); a
  name in such a cell is not matched. Text inside an image is not seen.
- A spreadsheet stores a price as a bare number: a price belongs on the
  deny-list without separators too, or a cell holding it is not matched.
- Commit messages and branch names are published too and are not files;
  nothing scans them.
- CI is detection, not prevention: by the time it runs, the pushed branch is
  public. The hooks are the prevention, and they run only where a deny-list
  file exists.

## As built (2026-10-12)

- `scripts/check_public_repo.py`: `DW_PUBLIC_REPO_DENYLIST` names the
  deny-list (UTF-8, one term per line, `#` comments). Not set: on a
  developer machine it prints a banner that customer data was NOT checked
  and exits 0; with `CI` set it exits 1. `--staged` reads the index's copy
  of each staged file (`git show :path`), not the working tree. It always
  checks that `.gitignore` covers `docs/design/` and `docs/**/*.docx`
  (`git check-ignore --no-index` on three probe paths) and that nothing
  there is tracked; that half needs no deny-list.
- `.gitignore`: `docs/**/*.docx` added beside `docs/design/`.
- CI: `security-scan` job, after the workspace sync, writes the
  `PUBLIC_REPO_DENYLIST` secret to `$RUNNER_TEMP` and scans every tracked
  file. A pull request from a fork gets no secrets, so the step fails there.
- Tests: `apps/api/tests/unit/test_public_repo_guard.py` (19, 26 after the
  review, each in a
  throwaway git repo with the real `.gitignore`); `scripts/test_claude_hooks.sh`
  gains the gate case. Mutations run, each red then restored: the scan
  removed (9 red), diacritic folding off (5), CI not detected (1), zip not
  opened (2), PDF not opened (2), XML tags kept (1), character references
  kept (1), staged mode reading the working tree (1), allow-list ignored
  (2), deny-list inside the checkout accepted (1), an unreadable file
  passing (1), an empty deny-list accepted (2), whitespace in a term taken
  literally (1), `docs/**/*.docx` removed from `.gitignore` (4), and the
  gate's call removed (2 hook cases).
- Measured: a full-tree scan of this checkout takes about 1.5 s; with a
  fictional deny-list it found a PDF hit (`M03…pdf[page 1]`) and a
  spreadsheet hit (`M01…xlsx[xl/worksheets/sheet1.xml]`), and the git hook
  blocked a staged file through `pre-commit run` in a throwaway repo.
- For a person: create the repository secret `PUBLIC_REPO_DENYLIST` (the
  terms, one per line), and to run the guard locally put the same list in a
  file outside the checkout and set `DW_PUBLIC_REPO_DENYLIST` to its path in
  the shell profile (the gate does not read `.env`).
- Security review (reviewing-feature-security, 2026-10-12): boundaries 1-3
  and 5 do not apply (no table, route, agent reach or audit write). 6
  (defaults) is the point of the change: no deny-list in CI, an empty or
  unreadable one, and an unreadable file all fail, each with a test that goes
  red when the refusal is removed. 4 (untrusted content): the CI step runs
  the checkout's own copy of the script with the secret in its environment,
  so a branch pushed to THIS repository could change the script to print the
  deny-list into a public log. Fork pull requests get no secrets; the
  exposure is to people with write access, who can already read the secret's
  purpose but not its value. Left as is and named here. (Corrected in review:
  running `main`'s copy of the script would not close this, since such a
  branch can change the workflow too; see "Review".)
