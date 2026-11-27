# Shared DW1–DW2 work — what is still missing, as tickets

The "Còn thiếu" rows of `docs/dev/viec-chung-dw1-dw2.md` (written 2026-11-26),
each checked against the code on 2026-11-27 (after DW1 tickets 70–85) and
turned into a ticket here, pointed at the Sales ticket that already owns it,
or marked done. Tickets: `.claude/plans/shared/issues/NN-<slug>.md`. The doc's
rows now say which.

## State

- 2026-11-27, **opened** (Đạt: "lên ticket và giải quyết các việc chưa
  làm"). 36 tickets: 33 ready-for-agent, 3 needs-info. Nine rows were
  already done in the code; twelve stay with the Sales ticket that already
  owns them (one owner per fact: no second ticket opened), almost all
  waiting on Proterial IT, a UAT session or the plant; one is the DW2 team's.
  None built yet.

## Tickets

| #   | Ticket                                                        | Status          | Size | Blocked by |
| --- | ------------------------------------------------------------- | --------------- | ---- | ---------- |
| 01  | Mail-folder watchdog (⚑ UAT)                                  | ready-for-agent | S–M  | —          |
| 02  | Bravo watch guards the target in use, and its page (⚑ UAT)    | ready-for-agent | M    | —          |
| 03  | Admin page: each mailbox's state                              | ready-for-agent | M    | 01         |
| 04  | Gateway client and approval stamp out of `dw_sales`           | ready-for-agent | M    | —          |
| 05  | Identity links owned by the platform                          | ready-for-agent | M    | 04         |
| 06  | Admin page for identity links                                 | ready-for-agent | S–M  | 05         |
| 07  | Shadow mode into `dw_agent_runtime`                           | ready-for-agent | M    | —          |
| 08  | Assignment on the platform; "Nhận việc"                       | ready-for-agent | M    | —          |
| 09  | Hand over every open case of a person away                    | ready-for-agent | M    | 10         |
| 10  | Workload per person for the head                             | ready-for-agent | M    | —          |
| 11  | Approval reminders/escalation on the platform; who was told   | ready-for-agent | M    | —          |
| 12  | Hand a pending approval to a colleague                        | ready-for-agent | M    | —          |
| 13  | Approve on a phone                                            | ready-for-agent | S    | —          |
| 14  | DW1: decide versions in "Việc cần làm"                        | ready-for-agent | M    | —          |
| 15  | One "Việc của tôi" across every DW                            | ready-for-agent | M    | —          |
| 16  | Notification preferences and quiet hours                      | ready-for-agent | M    | —          |
| 17  | Typed chat blocks (card, confirm, choice, table)              | ready-for-agent | M    | —          |
| 18  | Approve or return in the chat                                 | ready-for-agent | M    | 17         |
| 19  | Small forms in the chat                                       | ready-for-agent | M    | 17         |
| 20  | Next questions after an answer; notice while the widget is closed | ready-for-agent | S | —      |
| 21  | Rate an answer, kept for the eval                             | ready-for-agent | S    | —          |
| 22  | @mention in a case's chat                                     | ready-for-agent | M    | —          |
| 23  | Chat attachment: upload, scan, read                           | ready-for-agent | M    | 17         |
| 24  | The answer reads the attachment                               | ready-for-agent | M    | 23         |
| 25  | Mail signature                                                | ready-for-agent | S    | —          |
| 26  | Nightly replay of recorded saves (switch off)                 | ready-for-agent | M–L  | 02         |
| 27  | DW2 case chat; widget and case-chat layout in `@dw/ui`        | ready-for-agent | M    | —          |
| 28  | DW2: send an RFQ and decide a PR from its chat                | ready-for-agent | M    | 17, 18, 27 |
| 29  | DW2: a buyer per PR, given, reassigned or claimed             | ready-for-agent | M    | 08         |
| 30  | DW2: RFQ with the PR's drawing and spec                       | ready-for-agent | S–M  | —          |
| 31  | Gateway: PR create and edit (DW2), pending                    | ready-for-agent | M–L  | 04         |
| 32  | Gateway: PO from PR and PR approval (DW2), pending            | ready-for-agent | M–L  | 31         |
| 33  | DW2's side of a Bravo write                                   | ready-for-agent | M    | 04, 05, 31 |
| 34  | Delegate approvals while away                                 | needs-info      | L    | Đạt        |
| 35  | One conversation store, the propose/confirm protocol (ADR)    | needs-info      | L    | Đạt        |
| 36  | Reply in the customer's thread                                | needs-info      | S    | a flow measured |

31 and 32 need the 11-26 trace file (`02-trace-3.csv`) and the local
layouts under `docs/proterial/` (gitignored): they run on Đạt's machine.

## Build order (codeable ones)

1. **Unblock DW1's UAT first:** 01 (a dead flow is the real mail risk), 02
   (a UAT-only gateway is otherwise paused by its own watch).
2. **Lifts DW2 builds on** (each makes a second copy unnecessary): 04 → 05 →
   06; 07; 08.
3. **Approvals and notices for everyone:** 11, 12, 13, 15, 16.
4. **DW1 chat and work, on the shared frame:** 17 → 18, 19; 20, 21, 22;
   23 → 24; 14; 10 → 09; 03; 25; 26 (after 02).
5. **DW2 lifts:** 27 → 28; 29 (after 08); 30; 31 → 32 → 33 (after 04, 05).

## Blocked, and on whom

- **Đạt:** 34 (what a delegation is), 35 (the conversation ADR), 36 (a test
  flow with a reply action); defaults for 01 (quiet hours) and 11 (reminder
  hours); 26's switch (may an agreeing replay keep writes going); 25 (does
  Outlook add its own signature); 27 (review the `@dw/ui` props); 30 (buyer
  uploads); DW1 mail retention term and keep rule (Sales 84).
- **Proterial / Đạt:** 29's automatic buyer rule and whether only the
  assigned buyer may act.
- **Proterial IT:** the UAT read and write logins, scripts 07/08/10 (Sales
  63, 75, 85); EXECUTE on the PR approval procedure (32); the AD federation
  (Sales 64).
- **UAT session (Đạt at Proterial):** the proofs that switch on cancel,
  split, create (Sales 71–73, 52), a unit-price change trace (52 G), a PO
  date change trace (32), each DW2 kind's proof (31, 32); latency through
  Cato and the real iPhone (Sales 83, 48).
- **The plant host:** the model's `--attest` run (Sales 57), the host itself,
  GPU, the CI runner and billing (Sales 83, 84).
- **The DW2 team:** feedback on the dev guide from their first run.

## Done since the doc (checked in the code, 2026-11-27)

- Assign in chat (DW1): `0135304b` (`dw_sales/application/assistant.py:1367`).
- Push from the platform's `deliver` for every DW: `04769aab`
  (`apps/worker/src/dw_worker/consumers/web_push_delivery.py`).
- Push off at sign-out: `e3e9c891`.
- A case reaching a PIC's turn (a routed mail that opens or moves a case) is
  pushed: `04769aab` with the follow-ups' `your_turn`
  (`dw_sales/domain/followups.py:746`).
- DW2's morning brief: already there before the doc, `a6924ee3`
  (`dw_purchasing/domain/brief.py`).
- Model drafts sent from "Gửi từ hộp thư của tôi": `1e867f0c` (Sales 76).
- Gateway saves a stored SO (`Edit`): `82ea1b73` (Sales 70).
- Gateway runs `CreateProcess` after a write: `22975464` (Sales 74).
- Command right read from Bravo: `0f70cedf` (Sales 75; script 10 fills it).
