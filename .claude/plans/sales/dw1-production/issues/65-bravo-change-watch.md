# 65 — Watch Bravo for change, and say so before a PIC meets it

Status: ready-for-agent (offline against recorded definitions; live after IT's read login)
Blocked by: 63 (the gateway computes the fingerprint; only it holds the credential)
Category: enhancement (ADR 0027, decision 4)

## Why

Đạt (11-21): Bravo's vendor and Proterial's admins will change Bravo without
telling DW, and asking them to commit to telling us is the wrong lever. DW
checks on a schedule, notices what changed, and says so. A change DW can
follow does not stop anything. A change it cannot follow stops only the
writes that depend on it, before a PIC's write meets it.

## Shape

- **What is fingerprinted.** The gateway computes it with its read login,
  plus `VIEW DEFINITION` on the listed objects only.
  - **Layouts and templates.** The layouts and Import templates DW runs:
    `B00Layout` / `B00LayoutData` per form, `B00ImportSetting` per template.
    Each is recorded with its `ModifiedAt` and `ModifiedBy`.
  - **Engine wiring.** The `B00Command` rows of those screens (module and
    `CtorArgs`).
  - **Columns** of every table DW reads or writes: name, type, length,
    nullability, default.
  - **Triggers** on the written tables: their definition hash and whether
    each is enabled.
  - **Bravo routines DW relies on.** The definition hash of every procedure
    and function the rule runner calls, plus the context parser
    (`ufn_sys_GetUserIdFromContext_Info`) and the permission functions.
  - **The client version** seen in the connected sessions' application name.
- **When.** A worker lane, `bravo_watch`, runs every 30 minutes during
  7–19h (Vietnam time) and once at night. Before each write, the gateway
  compares its cached fingerprint, which costs nothing. The lane is in the
  worker and asks the gateway for the fingerprint, so the decisions stay in
  the platform and the gateway only measures.
- **History.** Every fingerprint that differs from the last one is stored, as
  a tenant-scoped, append-only row. That history is also the answer to "how
  often does Bravo change".
- **What a change does.** Each write kind declares what it depends on, so a
  change stops only the kinds that touch it.

  | Change | Action |
  |---|---|
  | A layout changed. Every rule still parses, and the nightly replay of recorded saves gives the same or an explained result | **Writes go on.** A notice says DW follows Bravo's new rule X, with the diff of the rule. |
  | A layout holds a rule the runner cannot evaluate (new function or component) | That screen's writes **pause**. The notice names the rule. |
  | A column, a trigger, a routine DW calls, or the context parser changed | The dependent write kinds **pause**. Reads go on while their columns still exist. |
  | The client version changed | Notice. The nightly replay must pass before writes resume. |
  | UAT differs from production | **Early warning**: "Bravo UAT has X, production does not yet". An upgrade is usually tried on UAT first; nobody has to promise it. |

- **Nightly replay.** For each screen DW writes, the recorded saves (the
  trace, ticket 59) are run through the runner on today's layout, and the
  result is compared with yesterday's. Every rule of every layout DW uses is
  parsed, so an unknown function is found at night, not on a PIC's write.
- **Notice.** It goes through the platform's notifications (in-app and push)
  to the people holding `bravo.watch.read`, and to FPT support.
  - **Plain words:** what changed, when, by which Bravo user (Bravo's own
    `ModifiedBy`), which DW functions it affects, and whether they run or
    are paused.
  - **Audit:** as the lane itself (`lane_audit_event`, `system:bravo_watch`).
- **Resume.** A person accepts the new fingerprint as the baseline, after the
  replay passes on UAT. The acceptance is a permission
  (`bravo.watch.accept`), checked where the baseline is written, and it is
  recorded with who accepted it and why. Nothing resumes by itself after a
  pause (fail closed).
- **Bravo unreachable.** The status reads "could not check since HH:MM",
  never "unchanged". Writes pause after the cached fingerprint passes its
  age limit.

## Acceptance

1. Each row of the table is a test on recorded definitions:
   - a layout edit that parses goes on, with a notice;
   - a layout with an unknown function pauses only that screen;
   - a column change pauses only the kinds that use it;
   - a trigger change pauses only the kinds that write that table;
   - a UAT-only difference gives the early warning;
   - unreachable Bravo reads "could not check".
2. A pause holds until a person with the permission accepts the baseline. A
   person without it is refused where the baseline is written.
3. Mutation: an unchanged-on-error default, or a resume without acceptance,
   turns a test red.

## Comments

Script 06 section 11 measures how often Bravo changed in the past three years
(the last-modified dates of layouts, templates, routines, triggers and tables).
Those are only the last change of each object, so the counts are a lower bound.
