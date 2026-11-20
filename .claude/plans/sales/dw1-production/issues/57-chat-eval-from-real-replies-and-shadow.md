# 57 — A chat eval from the PICs' real replies, run in shadow from day one

Status: needs-triage
Blocked by: 56
Category: evaluation

## Why

The open thread-intent step measured 0.816 on Strata, under its 0.85 bar, and
is switched off. Two things follow:

- the case assistant must be measured on the six PICs' own way of writing
  before it acts by itself;
- a model upgrade must be a re-run of this eval, not a prompt rewrite.

## Shape

- **Shadow from go-live.** The assistant's tool choice is recorded next to what
  the PIC actually did. Each disagreement becomes a labelled example (ADR 0015).
- **Examples.** The 2–3 nearest examples are retrieved for each message,
  instead of a long fixed list.
- **Dataset.**
  - real replies: abbreviations, typos, mixed Vietnamese and English;
  - prompt-injection mails;
  - wrong-case requests;
  - missing evidence.

  Graders are keyed `sales.<gate>` in `dw_sales.testing`.
- **Switching on.**
  - A tier is switched on per decision kind once that kind passes its bar.
  - A new model is adopted only when the whole eval passes.

## Acceptance

1. The eval runs in CI's smoke set.
2. Each tier switch cites the run that passed.

## Comments
