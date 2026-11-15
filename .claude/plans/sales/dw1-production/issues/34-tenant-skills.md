# 34 — Skills: a tenant teaches DW1 a kind of mail in words

Status: ready-for-agent (behind 30's gate); held 2026-11-16 until Đạt decides dw_sales ADR 0014 (deep agent with tenant skills), under which it is rebuilt
Blocked by: 33
Category: enhancement

## Why

dw_sales ADR 0012 decision 3 (grilling Q11).

## Shape

- A skill is a tenant version (the `sales.rules` flow): words, a scope
  (one customer or all), proposed by a PIC or the head from a triage card,
  approved by the head (never the proposer) after a dry run showing the
  triggering mail read with and without it.
- A skill adds no tool, scope, recipient or number; the reading stamps
  the skill versions used.

## Acceptance

1. The proposer cannot approve their own skill.
2. A skill text asking for a tool or another customer changes nothing a
   tool can reach (negative test).
