# 01 — The model is Qwen3.8-Flash-Next on Strata, attested on every set

Status: done (2026-11-16, closed by Đạt: Strata on the plant is in order)
Blocked by: none
Category: enhancement

## Why

Đạt, 11-10: Qwen3.8 only, no Qwen3.5-9B (`docs/adr/0025`). Measured 10-26
on six DW1 sets on an RTX 3090: every bar passed. Not measured: DW2's sets,
the Q&A sets, the security cases, the plant's GPU.

## Shape

- `configs/models/onprem.yaml`: every route to the Strata model under a new
  `routing_policy_version`; thinking stays off; still no fallback route.
- `scripts/warm_model.py` and `model-warm` warm Strata, not Ollama.
- The on-prem compose runs Strata from a saved image; the offline bundle
  carries it with the weights.

## Acceptance

1. Every DW1 and DW2 golden set, the assistant sets and the security cases
   pass their bars through the profile on the RTX PRO 4000; the results go
   into the plan file.
2. The streamed chat (`released`) still holds every word until it passes.
3. With Strata down, every step degrades to a person, asserted by a test.
4. The licence allows on-premises commercial use, written down.

## Comments

- 2026-11-16, Giang's home lab, not attested (not the plant's RTX PRO 4000).
  Every DW1 set with a model step (the 23 in `test_live_lane.MODEL_STEPS`),
  live through the `onprem` profile 1.3.0 on Strata
  (`qwen3.8-flash-next-q2_0`, thinking off), one at a time. Every case of
  every set passed, the security cases (injection, cross-tenant, missing
  evidence) included, and no call was unavailable. Bars are reported, not
  enforced: they bind only through `--attest`, which was not run. The 9B
  column is the last live report on Qwen3.5-9B (GTX 1080; its date given).

  | Dataset | Bar | Qwen3.5-9B | Strata | p50 / p95 per call | Bar |
  | --- | --- | --- | --- | --- | --- |
  | sales_reply@2.0.0 | 0.85 intent, bar set | 0.816 (11-15) | 0.796 | 1.7 / 2.1 s | fail |
  | sales_thread_agent@1.0.0 | 0.85 intent, no false accept | 0.85 (11-15) | 0.85, 1 false accept (RP16) | 2.0 / 2.4 s; turn 3.0 / 3.5 s | fail |
  | sales_reply_draft@1.0.0 | 0.85 complete | 0.833 (11-15) | 0.917 | 2.6 / 4.2 s | pass |
  | sales_change_request@1.0.0 | 0.85 right change | 1.0 (11-15) | 1.0 | 1.5 / 1.8 s | pass |
  | sales_descriptions@1.0.0 | 0.70 gold in candidates | 0.667 (10-29) | 0.933 | 9.0 / 12.6 s | pass |
  | sales_intent@1.0.0 | 0.90 kind | 0.902 (11-13) | 0.978 | 1.4 / 1.6 s | pass |
  | sales_rfq@1.0.0 | 0.85 right field, VI/EN | 0.828 (11-13) | 0.833 | 3.0 / 4.0 s | fail |
  | sales_handoff@1.0.0 | 0.85 right | 0.877 (11-13) | 0.877 | 1.8 / 2.3 s | pass |
  | sales_layout@1.0.0 | 0.90 right | 0.977 (10-29) | 0.994 | 2.7 / 2.9 s | pass |
  | sales_po_body@1.0.0 | 0.85 right field | 1.0 (10-30) | 1.0 | 4.1 / 4.4 s | pass |

  Sets with no bar (on request, not a `ModelStep`), every case passed:
  assistant (right 1.0, 5 of 8 answers in the model's words; 1.2 / 1.8 s),
  catalog_columns (3/3; the 9B read 2/3; 1.8 / 1.8 s), customer_reminders
  (2.6 / 3.2 s), design_text_replies (1.8 / 2.2 s), finding_explanations
  (2.9 / 3.9 s), morning_brief (2.2 / 2.4 s), pc_dates (2.0 / 2.5 s),
  screening_followups (2.3 / 2.9 s), sender_customers (1.1 / 1.5 s),
  thread_summaries (2.6 / 2.9 s), rule_drafts (2.2 / 3.7 s), rule_words
  (1.7 / 2.2 s), salesorder_rules (2.8 / 3.8 s).

  The thread agent called tools where the 9B did not: 57 tool calls in 72
  turns (2 on the 9B), 56 turns with a tool, at most 2 in a turn, 129 model
  calls in all; the expected tool was called in half the turns that needed
  one (0 on the 9B); by tool, case_snapshot 26, case_by_number 24,
  thread_messages 4, conversion_lookup, lead_time and pc_status 1 each; no
  foreign record. Its one false accept, RP16, read a change request as
  `accepts` too. Japanese is the weak language on both intent readings
  (reply 0.647, thread agent 0.611). The RFQ misses are mostly a line's
  quantity left to a person; nothing was invented.

  Slowest call of the whole run 12.6 s (descriptions). Strata unloads an
  idle model and the first call after took about 32 s (by hand). A
  26k-token prompt answered in about 10 s; the profile keeps
  `max_input_tokens` 6000 (why: `configs/models/onprem.yaml`). Strata serves
  no embeddings (POST /v1/embeddings refused 403), so bge-m3 still needs a
  server. Recorded answers were not rewritten: the smoke and several unit
  and API tests replay the 9B's, and a new recording is its own change.

## Done

Closed 2026-11-16 by Đạt, who confirmed the Strata set-up on the plant
is in order (profile, warm script, offline run and the measurement he
oversaw). Not re-measured in this repository after the home-lab run in
Comments: the three bars that run missed (reply 0.796, RFQ 0.833, the
thread agent's one false accept) stay open in their own tickets and keep
those steps off.

- 2026-11-16: `configs/models/onprem.yaml` 1.3.0, every chat route on
  `qwen3.8-flash-next-q2_0`, thinking off, no fallback, timeouts and
  `max_input_tokens` kept (measured above); release manifest regenerated.
- The profile test reads the model from the profile and holds every chat
  route to one model (ADR 0025).
- `scripts/warm_model.py` was not Ollama-bound (OpenAI-compatible calls,
  the key from `DW_ONPREM_MODEL_API_KEY`); its text now says so, and it
  warmed Strata (1.0 s; bge-m3 not served there).
- Acceptance 3: each `ModelStep` already had a model-down test except the
  change request; `test_the_model_down_reads_nothing_and_a_person_types`
  added.
- **2026-11-16 afternoon, the plant's own GPU (RTX PRO 4000 Blackwell 24 GB,
  Strata v0.2.14 on Windows, Q2_0, one slot, vision on), measured, not
  attested** (no plant database yet). Every DW1 model-step set, live through
  the `onprem` profile from the laptop over Tailscale, at `480d269d` plus the
  uncommitted ticket 37 work in the tree; 49 minutes for all 31. First found:
  with `--parallel 3` Strata refuses `logprobs` beyond one token, and the
  structured route asks for them (1.4.0), so every reading on it failed;
  Strata now runs one slot (Đạt chose it, `ops-hardening.md`). On one slot:
  28 of 31 sets passed every case. Failed cases: `sales-handoff-notation-
  records` ("another customer's record settled a value", HO17) and
  `sales-rfq-notation-records` ("a record read a value wrong"), both ticket
  37's uncommitted notation records, to its session; `sales-rule-draft-golden`
  (T-VI-2 marked ready with 8/9 columns right). Bars met: change_request 1.0,
  description_attributes 0.933 (0.7), skill_document_forms 0.888,
  request_handoff 0.877, skill_handoffs 0.863, message_intent 0.989,
  layout_proposal 0.994, skill_mail_kinds 1.0, po_body_extraction 1.0,
  skill_reply_drafts 0.917, salesorder_skill 1.0, triage_card 1.0. Missed
  (bar 0.85 each): reply_intent 0.837 (lab 0.796), reply_draft 0.833 (lab
  0.917: worse here), rfq_extraction 0.838 (lab 0.833), skill_intents 0.717
  (lab 0.800), thread_agent 0.85 not passed (the bar's other condition). p50
  per call mostly 0.9–2.4 s; descriptions 7.2 s (p95 9.1). Acceptance 1
  still owed: the attested run once DW runs on the plant, after the misses
  are worked or the steps left off.
- **2026-11-16 evening, the plant's Strata again (RTX PRO 4000, Q2_0, one
  slot, over Tailscale from the laptop), measured, not attested:** the two
  notation cases that failed in the afternoon now pass after `01bd501c`
  (ticket 37's graders tell a record's effect from the live model's
  variance). `sales_handoff@1.0.0` 7/7 (`sales-handoff-notation-records`
  passes; golden right 0.877, wrong 0, invented 0) and `sales_rfq@1.0.0`
  10/10 (`sales-rfq-notation-records` passes; golden right_field 0.85, wrong
  0). Same day, `skill_intents` before any change: bar set 0.700 (the
  afternoon's 0.717), false accepts RP16 and RP17 (ticket 40 continues).
