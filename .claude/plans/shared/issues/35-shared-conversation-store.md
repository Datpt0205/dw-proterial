# 35 — One conversation store for every DW, and the propose/confirm protocol

Status: needs-info (Đạt: an ADR to decide)
Blocked by: Đạt's decision
Category: chat / architecture

## What

§1: "Một kho hội thoại chung cho mọi DW (DW1 theo hồ sơ + 1 chung; DW2 theo
phiên có tên) và giao thức đề xuất/xác nhận" (L). Checked 2026-11-27: two
stores, `sales.assistant_sessions/assistant_turns` (one general and one per
case per person, RLS by user, migration `bfe2d1aeadcd`) and
`purchasing.assistant_sessions/assistant_turns` (named sessions).

## Why it waits

Where a turn lives decides what it can be bound to. A case's turn proposes
effects bound to that case's version and is taken in the case's transaction
(the confirm, the shadow label), which argues for keeping each context's
store; one platform store argues for one history, one retention rule, one
search. That is an architecture decision (CLAUDE.md: record it, do not
deviate silently).

Recommended, for the ADR: **keep each context's store**, share the protocol
and the frame instead: the typed blocks (ticket 17) and the
propose → confirm → server re-check cycle as a platform contract
(`dw_platform.domain.chat_blocks` plus a written protocol), one frame in
`@dw/ui` (ticket 27); a platform store only for the general conversation
that belongs to no case, if Đạt wants one history across DWs. Whether a
case's conversation becomes shared among the people working the case (today
each person's own) is part of the same ADR (ticket 22 depends on it).

## Acceptance (once decided)

- The ADR in `docs/adr/` with status, the protocol written down, and a
  ticket per slice it implies.

## Owed

- Đạt: the ADR's decision (store per context or one store; case
  conversations per person or shared).
