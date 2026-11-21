# 59 — A Bravo rule runner: execute the screen's own XML rules, not a copy of them

Status: in-progress — the SO screen's slice is done (2026-11-21); YCBG, quotation, PR and PO next. pending: script 03c (the shared template `BizDocEditor`) for creating an SO and for a line split
Blocked by: 49 before anything runs against Bravo; none for building it offline
Category: enhancement

## Why

Bravo's form logic (the SO screen: 404 field rules, 27 validators) is not
executed by SQL Server.

- It is stored as XML in `B00LayoutData` and `B00ImportSetting`.
- It is run by the Bravo client on each PC: `B00Command` maps `EDIT_BizDocSO`
  to the `DataEditor` module.

A write through the database therefore skips every rule. Copying the 404 rules
by hand would create a second copy that drifts. The rules are data, though,
and the vocabulary is small:

- 11 rule component kinds;
- about 20 expression functions;
- 22 Bravo procedures and functions, whose code we have.

So DW can run Bravo's own definitions, read at run time, and follow Proterial's
configuration as it changes.

## Shape

- Parse the screen's XML at run time:
  - evaluators per column on `ColumnChanging` / `ColumnChanged`;
  - validators, separated into blocking and warning by `bValidateWarning`;
  - server constraints with their procedures and parameters.
- An expression evaluator for Bravo's language:
  - EMPTY, ISNULL, IIF, CHILD, SUM, SUMIF, VLOOKUP, EXISTS, IN, DATEADD,
    CHARINDEX, CONVERT, UPDATEDCOLUMN, USER, GETDATE;
  - `Parent.<col>` for the header and `Exists(Detail)` for the lines.
  - Unknown syntax refuses the run; it never guesses.
- Server constraints call the same procedures, read-only, through the
  gateway's read login (ticket 63, ADR 0027).
- Output: the exact column set the client would `INSERT`/`UPDATE`, the warnings
  for the PIC, and the blocking reasons.
- Scope order: SO lines (dates, split, cancel, quantity), then SO creation,
  then YCBG, quotation, PR, PO.

## Acceptance

1. Replayed on the 11-20 UAT trace, the runner produces the same columns and
   values the client sent, for every saved SO and YCBG operation.
2. Each validator in the SO layout has a test that fires it.
3. A layout changed in Bravo changes the runner's behaviour with no code change
   (test with an edited copy).

## Done (2026-11-21, the SO screen, offline)

- `packages/python/dw_bravo` — Bravo shared by DW1 and DW2, standard library
  only, no driver (ADR 0026 untouched; ticket 49 still owes the amendment):
  - `layout.py` reads a `<DataSource>` layout as data: tables, per-column
    `ColumnChanging`/`ColumnChanged`, row events, rules defined in
    `Evaluators`/`EvaluatorGroups` or inline at first use, validators,
    defaults, computed columns, temp columns; a DOCTYPE is refused; a rule
    defined twice differently refuses when used.
  - `expression.py` evaluates Bravo's language (ADO.NET DataColumn syntax plus
    Bravo's functions, `{=...}` substituted from the row). It refuses, never
    guesses: unknown syntax or function, CHARINDEX (base unmeasured), a value not
    in hand (`UNKNOWN` is never NULL), a case-only string difference, rounding
    on the half, mismatched types. A NULL rule condition reads as not true
    (ADO.NET's filter rule; the SO layout's `PriceIncludeTax=1` relies on it); a
    validator's NULL stays undecided.
  - `runner.py` is the client's engine: `load` (ServerLoaded; what cannot be
    learnt stays UNKNOWN), `edit` (cascading events), `check` (block, warning,
    undecided), `save` (ServerUpdating, then the exact UPDATE/INSERT column
    sets), and a trail of every value set, by rule or person (for ticket 62).
    Fail closed: an undecided blocking validator blocks; a plan made without
    the shared template is `provisional` and `may_write` is false.
  - `ports.py`: `ProcedurePort`, `ReferencePort`, `Session`; the offline
    adapter `adapters/recorded.py` answers only calls recorded with exactly
    these parameters. `testing/sql_trace.py` and `testing/replay.py` read an
    Extended Events CSV and replay a screen's saves; no data is in git.
- Contexts reach it only through their adapters: import-linter contract
  "Contexts reach Bravo only through their adapters" (shown BROKEN by a probe
  import in `dw_sales.application`, then kept).
- Measured on the 2026-11-20 UAT trace (`DW_BRAVO_TRACE`, local only): all
  6 saved SO UPDATEs reproduced column for column, each procedure the runner
  called matched one the client made with the same parameters; the person's
  edits were 8 columns in all, the other 17 written columns computed by
  the layout. The 2 INSERT saves (create, line split) are not replayed:
  `ConvertRate9` and `QuantityBox` of a new line are set by no rule in layout
  8212, so by the template (script 03c) or a lookup.
- Validators: 27 (17 block, 10 warning), each with a test (`DW_BRAVO_LAYOUTS`,
  local only): 20 fire; `CheckBizProcess` passes for the creator and is
  undecided otherwise (CHARINDEX); 6 have no `ClassName` (`NotNull` on the
  header and on lines, `NotNull_DocNo`, `LME`, `ItemCodeTmp_CheckEdit`,
  `NotnullCatalogry`) and are undecided until the template shows their kind.
- An edited copy of the real layout (the price band 150 → 250) changes the
  check with no code change; the same holds on the CI layout (rounding 2 → 0).
- Mutation check: 10 guards broken one at a time (fail-closed save,
  provisional write, template rule, case compare, half rounding, unrecorded
  call, DOCTYPE, NULL condition, UNKNOWN-as-NULL, money NULL), each turned a
  test red. CI runs 33 tests on a layout written for them; 30 more run where
  the data is.

## Comments

Measured facts and file locations: `docs/proterial/bravo/BRAVO-NOI-BO.md`
(gitignored).
