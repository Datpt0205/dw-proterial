# Hardcode audit, 2026-11-13

Đạt, 11-13: "rà lại toàn bộ code để xem chỗ nào đang hardcode để lấp liếm bug
hoặc các case khó". A read-only sweep of production code (DW1, DW2, platform):
22 findings (5 HIGH, 9 MED, 8 LOW), each verified by reading the code and,
where marked "checked", by running the parser; about 180 candidates dropped
(documented fallbacks, `is_deployed` gates, bounded caps that refuse, structural
mail-history separators). Fixed in batches; each batch's commit names the
findings it closes, and this file marks them.

- **A — deployed on fictional data (Sales):** 1, 7, 11.
- **B — DW2 attaches or reads wrong:** 2, 3, 13.
- **C — numbers, units, dates, currency:** 4, 5, 8, 9, 20, 21.
- **D — the rest:** 6, 10, 12, 14, 15–19, 22.

| #   | Sev  | Where                                                                                                                                         | Failure                                                                                                                       |
| --- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1   | HIGH | `dw_sales/application/snapshot_catalog.py:383-392`, `adapters/assembly.py:246-262`, `apps/api/src/dw_api/settings.py:147`                     | Deployed DW1 checks real POs against the mock catalog's ERP orders and open YCBGs, and the mock master lists until approved    |
| 2   | HIGH | `dw_purchasing/application/sourcing.py:657`                                                                                                   | A supplier's reply naming PR-12 attaches to PR-1 (substring match); at AI_AUTO the offer is recorded on the wrong case — fixed 2026-11-13 |
| 3   | HIGH | `dw_purchasing/application/intake.py:346,365`, `sourcing.py:376,389`, `follow_up.py:201`; `dw_agent_runtime/model/interpretation.py:50-57`    | `cut_to_tokens` cuts mid-line and spans are verified against the cut text: "1500" can pass as "15"; later lines vanish — fixed 2026-11-13 |
| 4   | HIGH | `dw_sales/domain/handoffs.py:230-279`, `application/handoffs.py:312`                                                                          | "3 km" reaches PC as 3 m when the model's span omits the unit; yards, kgs, spools pass as metres — fixed 2026-11-13 |
| 5   | HIGH | `dw_sales/application/design_text_reading.py:101-110,139`                                                                                    | Copper weight anchored by `str.find`: "2.5" accepted inside "12.5 kg/km"; kg/m or g/m taken as kg/km — fixed 2026-11-13 |
| 6   | MED  | `dw_sales/application/order_intake.py:179-195,1184-1207,1271-1278`                                                                            | Keyword tables are the default path (model step shipped off); a complaint about an order with a PDF reads as a PO             |
| 7   | MED  | `dw_sales/adapters/readers/layouts.py:71-84`, `readers/operations.py:89-93`                                                                   | The reader carries layouts keyed by mock customer codes; a real customer with the same code skips "first PO uncertain"        |
| 8   | MED  | `dw_sales/domain/rfq_reading.py:203-215`, `dw_purchasing/domain/mail_reading.py:159-178` vs `dw_sales/domain/master_data.py:149-186`         | "1.250" is 1250 in two parsers and refused as ambiguous in a third: one question, two answers — fixed 2026-11-13 |
| 9   | MED  | `dw_sales/domain/rfq_reading.py:336-342`, `dw_purchasing/domain/mail_reading.py:142,180-196`                                                  | Dates always day first: US "05/11/2026" becomes 5 Nov; "11/15/2026" silently swapped — fixed 2026-11-13 |
| 10  | MED  | `dw_sales/adapters/readers/text_parts.py:48-49,155-160,20-23`                                                                                 | The model sees ≤1000 rows, columns A–Z, no scanned pages of a mixed PDF; nobody is told                                       |
| 11  | MED  | `dw_sales/application/artifact_content.py:362-375`, `order_artifacts.py:264` vs `dw_purchasing/application/orders.py:88-91`                   | Sales' mock Bravo upload layout and mock mail copy are only noted when deployed (Purchasing refuses its mock)                 |
| 12  | MED  | `dw_knowledge/adapters/qdrant_index.py:38-47,320-328`                                                                                         | Any error whose text says "404"/"not found" becomes an empty search, read as "no evidence"                                    |
| 13  | MED  | `dw_purchasing/domain/master_lists.py:181-186` (used `automation_lane.py:766`, `sourcing.py:666`, `follow_up.py:120`)                         | A supplier contact on gmail makes gmail.com its domain: any verified gmail sender counts as that supplier — fixed 2026-11-13  |
| 14  | MED  | `dw_sales/domain/order_checks.py:65,279`, `artifact_content.py:50`, `overview_service.py:75`, `quotes_service.py:82`                          | Asia/Ho_Chi_Minh in code 4+ times while `working_hours.time_zone` is tenant config                                            |
| 15  | LOW  | `apps/web/app/sales/page.tsx:57`, `apps/web/app/sales/quotes/[caseId]/page.tsx:80,277-279`                                                    | "Due soon" 48 h / 1–2 days in the UI beside the policy's `hours_before_due` / `due_within_days`                               |
| 16  | LOW  | `dw_platform/domain/approval.py:115`                                                                                                          | A strict approval with no `makers` key excludes only the requester                                                            |
| 17  | LOW  | `dw_agent_runtime/adapters/docgen_client.py:137`                                                                                              | A reply with no `results` gives `[]`, read as "uploaded with no errors"                                                       |
| 18  | LOW  | `apps/api/src/dw_api/routes/v1/knowledge.py:30,125`                                                                                           | The route keeps its own `platform_admin` string and decides authorization there                                               |
| 19  | LOW  | `run_store.py:195`, `approval_codes.py:85`, `provisioning_repo.py:213,218`, `admin_console_repo.py:99`, `rfq_mails.py:106`, purchasing `store.py:216` | Constraint names found by substring in the error text (others read `constraint_name`)                                |
| 20  | LOW  | `rfq_reading.py:253-270`, `mail_reading.py:144-156`                                                                                           | "$" always USD, "¥" always JPY; the table exists twice — fixed 2026-11-13 |
| 21  | LOW  | `dw_sales/application/artifact_content.py:128`                                                                                                | `%d %b %Y` prints the month in the server's locale on customer documents — fixed 2026-11-13 |
| 22  | LOW  | `dw_sales/adapters/readers/ocr.py:51,197`; `pc_dates.py:64` + `routes.py:231` + `pc-dates.tsx:17`                                             | A scanned line under 30 confidence vanishes unflagged; the 8000-character PC paste limit written three times                  |

## Suggested fixes (from the audit)

1. Deployed: answer "ERP chưa nối" (a finding a person sees) instead of the mock fallback; refuse `sales_mailbox=mock` as Purchasing does (`wiring.py:650`, `worker/main.py:496`).
2. Use `mail_reading.occurrences(folded, fold(pr_no))`, which exists for exactly this.
3. Refuse as `too_long` to a person (as `dw_sales/application/rfq_reading.py:126-131`), or cut on a line boundary and mark the reading truncated; never verify against a mid-line cut.
4. Accept only known metre spellings (`rfq_reading._METRE_UNIT`) and read the word after the span in the full text.
5. `FoldedText.locate(bounded=True)` and require kg/km right after the span.
6. With the model off, test the specific routes before `_PURCHASE_ORDER`; a mail with no document goes to a person as `other` rather than guessing PO.
7. Ship no customer-keyed layouts when deployed.
8. One number parser that refuses ambiguity unless the customer's locale is known.
9. Date order from the customer/supplier record, or refuse when both numbers ≤ 12.
10. A `truncated`/`partial` flag that routes to a person.
11. Refuse the mock upload layout when deployed.
12. `exc.status_code == 404` with `collection_exists`; raise otherwise.
13. Match by address for public mail providers, as Sales' sender ledger does.
14. Read `working_hours.time_zone` everywhere.
15–22. Read from the policy; raise on a missing `makers` / `results`; `PLATFORM_ADMIN_ROLE` or a scope via `authz.require`; `getattr(exc.orig, "constraint_name")`; one currency table, a bare symbol unknown; month names per language; flag low-confidence OCR lines; one owner for the 8000 limit.

## Found while fixing

- Batch B (11-13): `cut_to_tokens` now cuts on whole lines only; the DW1
  callers verify against the whole text, but `dw_sales/application/handoffs.py`
  reads values from a cut text and drops lines past the cut with no flag:
  taken into batch C with finding 4 (refuse `too_long`, as `rfq_reading` does).
- Supplier versions already stored keep any domain the removed derivation
  wrote; a re-import of the supplier sheet clears them (only mock data today).
- Batch C (11-13): the hand-off cut above is closed (a text that does not fit
  is an `unavailable` hand-off counted `too_long`, never cut). Numbers, dates
  and currency are read by one platform module, `dw_platform.domain.notation`,
  by Sales (RFQ, PO body, hand-off, Design reply, master-data import) and
  Purchasing (PR mail, offer, confirmation). A decimal point alone (`0.95`)
  settles only a comma as thousands, never a dot as a decimal: the golden
  Vietnamese PO writes `6.100 m` beside `đơn giá 0.0420`, and reading the dot
  as decimal would have made it 6.1 m.
- Batch C's cost, measured on the recorded replays (decision owed, not taken
  here): `sales-rfq-golden` vi_en right_field 0.828 against its floor 0.94
  (`evals/expected/sales_rfq_golden.json`) and the live bar 0.85;
  `sales-handoff-golden` 0.849 against 0.94 and 0.85; `sales-rfq-flow` opens
  mock M37 ("1.200 m", "3.000 m", nothing else settling them) with both
  quantities for Sales (`rfq_incomplete`). Every miss is a value left to a
  person, none invented. The golden mails and M37 were left as written (M37's
  recorded answers are keyed by its text); fixtures that feed flows and
  security cases gained a settling value instead: the PO-body fixture's
  Vietnamese prices are written `0,0420` (its cross-tenant case needs a PO
  that reads), Purchasing's Q03/Q04/P06 an order minimum, a replaced price, a
  meeting date. Options: accept and re-record the floors; let a customer's or
  supplier's document language settle it (the audit's first suggestion, ruled
  out on 11-13); or let a zero-decimal currency (VND, JPY) settle an amount
  written in it ("98.000 VND" is refused today unless the mail says more).
- Sales' readers (`adapters/readers/excel.py:794`, `pdf.py:693`) print a bare
  `$` or `¥` as written now that `parse_currency` no longer maps it; a form
  that prints only `$` reaches the currency check as `$`, for a person.
- `dw_agent_runtime/model/figure_check.py` `_AMOUNT` lists currency words for
  a different question (does prose name an amount); left as is.
- `adapters/mock/generate_attachments.py:830,843` still formats `%b`: mock
  fixtures only, never a customer document.
