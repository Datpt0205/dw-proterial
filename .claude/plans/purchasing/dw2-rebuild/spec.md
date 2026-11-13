# DW2 rebuilt on Proterial's real purchasing flows

Status: ready-for-agent from T2 on; T1 is the BA's; some tickets wait on
Proterial or on Bravo's API, as each row says
Owner: Đạt
Started: 2026-11-13

## Why

DW2 was built on assumptions before the survey. The BA's two flows
(2026-11-13) show the real order: source and quote first, the PR raised and
approved on Bravo, the PO approved on paper, no budget step. The comparison
of both flows with what is built found DW2 in the reverse order: of 53 rows
in the raw-materials flow 1 is built, 14 partly; of 48 in the tools flow 1 is
built, 19 partly.

Sources, outside git (the repository is public):

- `Downloads/DW2.drawio` "PURCHASING – NGUYÊN VẬT LIỆU (NVL): MỚI + MASS" and
  `Downloads/DW2-1.drawio` "PURCHASING – CCDC / MÁY MÓC / DỊCH VỤ", decoded in
  `D:\dw-tools\dw1flow\dw2.txt` and `dw2-1.txt` (steps MỚI-, MASS-, CÓ-,
  CHƯA-, CHUNG-xx; gates G0, GM1–5, GS1–4, GC1–7, GN1–4, GO2–5, GIC; the
  BA's open points OP-02…OP-25);
- the comparison, `Downloads/proterial/DW1-flow-review/GAP-DW2.md`: the
  step-by-step table (§1), what to keep, change or retire (§2), the diagram
  corrections (§3), the questions (§4), the tickets with their reasons (§5).

## Decided 2026-11-13 (Đạt)

`packages/python/dw_purchasing/docs/adr/0002-a-sourcing-case-is-dw2s-axis.md`:
the sourcing case is the axis; DW2 approves no PR (approval on Bravo, paper
PO); no budget check by default; no pre-selected quotation. ADR 0026's
11-13 amendment: DW2 writes Bravo only after a person approves exactly what
is written; the import file until the write API exists. DW drafts every
mail; a person sends it from their own mailbox. DW suggests suppliers from
internal data only (the plant's host does not search the internet).

## Kept, changed, retired (GAP-DW2 §2)

- **Kept:** reading mail and files in the sandbox; RFQs drafted by the model
  and sent by the buyer from their own mailbox; reading quotations and
  supplier confirmations; the Bravo import file; the brief and Q&A; master
  data from Excel (the stand-in until Bravo's API, widened by T6); the buyer
  typing Bravo's PO number (until R31).
- **Kept, not extended:** goods received and late lines, until OP-03 says
  what "Follow PO – FPT" covers.
- **Changed:** mail opens a sourcing case without a PR number; "Tôi cần
  mua…" becomes the sourcing request; RFQ before a PR; replies link by the
  DW number; the RFQ supplier cap gains a minimum of two and the exclusive
  exception; "Chọn NCC" becomes "PIC duyệt báo giá" with a reason; the PO
  comes from the PR approved on Bravo; reading a confirmation defaults to
  "AI làm, người duyệt".
- **Retired:** the tiered PR approval, re-approval past a tier, the
  `submission` switch and its permission set; the budget check (off now,
  code removed on Proterial's word); the scanned paper-PR page (paused,
  removed on Proterial's word: PR approval moved to Bravo).

## Tickets, in order

Build now on sample data:

| #   | What                                                                                                                                                                                                                                                                                  | Size | Waits on                   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | -------------------------- |
| T2  | No pre-selected or "rẻ nhất" quotation on the comparison                                                                                                                                                                                                                              | S    | none                       |
| T3  | Reading a confirmation defaults to "AI làm, người duyệt"                                                                                                                                                                                                                              | S    | none                       |
| T4  | Retire DW2's PR approval; the PIC confirms the check result before submitting on Bravo; a mismatch holds the case                                                                                                                                                                     | M    | ADR 0002                   |
| T5  | The sourcing case: four kinds (gate G0), RFQ before a PR, the DW number in RFQ subjects, mail without a PR number, Bravo's PR attached later                                                                                                                                          | L    | T4                         |
| T6  | Wider master data and sample files: item model, drawing number, maker, origin, group, English name; supplier AVL flag, last transaction date, documents with validity; exclusive suppliers; quotation number, date, MOQ, SPQ, delivery and payment terms                              | M    | none                       |
| T7  | One draft-mail path for every mail DW2 writes (ask the requester, supplier documents, negotiation, quotation to the requester, PO to the supplier, survey): a person reviews, edits and sends from their own mailbox                                                                  | M    | none                       |
| T8  | Required information per case kind as tenant rules; ask back when missing; re-check on the reply                                                                                                                                                                                      | S    | T5, T7                     |
| T9  | Supplier search: AVL first; the two-year gate; exclusive suppliers; at least two different suppliers unless exclusive (two quotes from one supplier count once), as tenant rules                                                                                                      | M    | T6                         |
| T10 | Mass materials: a still-usable quotation (validity, delivery term, MOQ), the PIC's "use it", else an RFQ to the last supplier                                                                                                                                                         | S    | T5, T6                     |
| T11 | Full quotation check: more fields read from mail and PDF; the seven-item checklist; the 13-criterion table; against the last purchase; quotation date not after the PR (tools with a quotation); clarification or negotiation draft; quotations in another currency kept in the table | L    | T6, T7; exchange-rate rule |
| T12 | Quotation and comparison sent to the requester (draft)                                                                                                                                                                                                                                | S    | T7, T11                    |
| T13 | Item code: search by model, drawing, maker, origin; warn on near matches, never choose; prepare creation data per group; a person creates it on Bravo                                                                                                                                 | M    | T6                         |
| T14 | Paper PO: "chờ ký" / "đã ký" when the PIC uploads the signed scan; the PO mail drafted only when signed, with that scan; RoHS/REACH reminder for new materials                                                                                                                        | M    | T7                         |
| T15 | Delivery dates a supplier confirmed, shown or exported for the PIC to enter in Bravo                                                                                                                                                                                                  | S    | T3                         |
| T16 | Remove what the real flow does not need (budget out of the default rules, paper-PR page paused, Q&A and brief on the new states) and fix the plan and `CONTEXT.md` lines that disagree with the code (GAP-DW2 §4.3)                                                                   | S    | Proterial for the removals |

Wait on Proterial: T17 new-supplier documents and the New Vendor
Application Form; T18 PR ↔ quotation ↔ drawing check on Bravo's PR export;
T19 the chemical form check; T20 the mass PR drafted for approval; T21
RoHS/REACH (new-material documents, survey from a BOM); T22 measuring the
model on real documents at the plant.

Wait on Bravo's API: T23 reads (R20–R23, R27, R30–R32, R35), each replacing
a file stand-in behind the same port; T24 writes after a person approves
(W11–W13, W15–W18), each with an idempotency key and the approver, read back.

T1 is the BA's: the diagram corrections in GAP-DW2 §3 (a PIC box "duyệt bản
sẽ ghi Bravo" before each of the six Bravo writes; OP-02 and OP-16 closed;
no internet search in MỚI-07; conditions written for the optional steps).

## Owed by Proterial (short; the BA's open points)

- Where the AVL and supplier documents live (Bravo or a file) (OP-13); the
  exclusive-supplier list: by item or group, who owns it.
- The two-quotation rule: an amount below which one is enough, who may waive
  it and with what reason; the 13 criteria confirmed.
- PR approval entirely on Bravo (OP-25); whether Bravo records a signed paper
  PO; the Bravo flow's go-live date (OP-04).
- Item-code creation guide per group; required fields per item kind; PR Form
  0251 (OP-22, OP-23); documents required per item kind.
- The chemical form's fields and the chemical list (EHS); BOM source and the
  survey form (OP-19); the mass demand sheet's format.
- What "Follow PO – FPT" covers after the PO is sent (OP-03); that budgets are
  no longer checked.
- How PRs and quotations in another currency are compared (rate, date).
