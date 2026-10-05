# 02 — Order intake core (deterministic) — amendment

Status: done (2026-10-05, amendment)
Blocked by: 01 (including its 2026-10-03 follow-up)

## What exists (working tree, not yet reviewed or committed)

Domain and application, with no framework imports:

- A keyword classifier (`OrderIntake.classify`).
- Excel and text-PDF readers in `adapters/readers/`, behind
  `PoDocumentReaderPort`.
- Convert-list mapping plus attribute candidates (`map_line`).
- The eleven original checks (`order_checks.py`), each finding stamped with
  `sales_order_rules@1.0.0`.
- An immutable `OrderCase`, with status `received → checked → in_review →
approved | correction_requested | rejected → uploaded_to_bravo →
confirmed`.

What stays: reading from cells, never from the body; the stamped rule
version; the injection test (M12). Everything below is a delta on top of that
code.

## Amendments

1. **One anchor type (G12).** Add `dw_sales/domain/anchors.py`:
    - `SourceAnchor(attachment_id, attachment_sha256, cell_ref | page + boxes | quote)`,
      where at least one of the three is required (validator), and
      `PageBox(x, y, w, h)` is in 0–1 of the page;
    - it replaces `orders.SourceAnchor` (sheet/cell or page/text-line) and
      `quotes.CellAnchor`.

    The PDF reader takes the boxes from pypdf text-run positions, and the
    text-line numbering goes. The Excel reader flags `hidden_sheet`,
    `hidden_row`, `hidden_column`, `font_matches_fill` and
    `formula_without_cached_value`. A value read from a flagged or unchecked
    region raises `value_uncertain`. Recorded in dw_sales ADR 0002.

2. **Order state machine (G1, G4, G8).** The state names and labels are in
   `packages/python/dw_sales/CONTEXT.md`, the one list; this item owns the
   transitions. Replace `OrderStatus` and `_NEXT` with:
    - `received → checked → in_review → prepared → uploaded_to_bravo → cross_checked → confirmed`.
    - `in_review → correction_requested` when any finding is `ask_customer`.
    - A new revision moves `checked | in_review | correction_requested |
prepared` back to `checked`. It marks the previous revision
      `superseded` and re-runs every check.
    - A revision after `uploaded_to_bravo | cross_checked | confirmed` goes
      to `change_review`. The output is the diff to apply in Bravo plus a new
      confirmation draft, with no new upload file. Then
      `change_review → uploaded_to_bravo` (the PIC states the change is
      applied).
    - A cross-check `trả lại` (reason required) goes back to `in_review`.
    - `closed(reason)` replaces `rejected`, reachable from every state before
      `uploaded_to_bravo`, with `reason ∈ duplicate | not_an_order |
superseded | cannot_supply`. `duplicate` and `superseded` link the
      case they refer to; `cannot_supply` needs a customer draft (06).
    - `cross_check_required: false` lets `uploaded_to_bravo → confirmed`. A
      test runs both values.

    Stamps: `prepared_by/at`; `bravo_so_no`, `bravo_recorded_by/at` and
    `bravo_entry_compared` (the PIC's statement that the Bravo entry was
    compared with the PO; all needed for `uploaded_to_bravo`);
    `cross_checked_by/at`; `confirmed_by/at`; and `case_version`. Lines,
    mappings and dispositions are edited only in `in_review` or `prepared`;
    an edit in `prepared` bumps `case_version` and returns the case to
    `in_review`. After `uploaded_to_bravo` nothing is edited in place: the
    checker's `trả lại` sends it back to `in_review`, which clears
    `prepared` and the Bravo stamps, so the corrected entry is recorded and
    cross-checked again.

3. **Maker/checker (G1, decision 7).** `cross_checked_by` must not be
   `prepared_by`, nor `bravo_recorded_by`, nor anyone whose hand-entered
   value (a `corrected_by_sales` value, or a PRV code typed for a
   `code_unmapped` line) is still on the case. A refusal is a
   `ConflictError` that names the rule ("tách nhiệm, WIV-03-012 bước 9").

4. **Per-finding disposition (G3, decision 9).** Add `FindingDisposition`
   with the spec's four values and the allowed set per code (spec table).
   `prepared` is refused while any finding other than `missing_noc_esf` is
   `open`, naming each one; `confirmed` is refused while `missing_noc_esf`
   is `open` (spec decision 9). `accepted` on `missing_noc_esf` takes a `by`
   that the application service has checked holds `sales.compliance.ack`.
   `Severity` stays, and `error` means blocking.

5. **Candidate confirmation (G13).** `MappingStatus` becomes `exact |
candidate | ambiguous | unmapped | candidate_confirmed(prv_code, by,
at)`. Today's `attribute` ("Sales confirms by approving") becomes
   `candidate`, which needs an explicit confirmation. Confirming a `prv_code`
   outside the line's computed candidates is refused. The one exception is a
   `code_unmapped` line, which has no candidates: Sales may type a PRV code
   that exists in the item master (for example once Design has created it).
   It is recorded as `candidate_confirmed` with the value state
   `hand_entered` (CONTEXT.md) and shown on the cross-check sheet.
   `prepared` (and so the
   upload file) is refused while any line is not `exact` or
   `candidate_confirmed`.

6. **Revised and duplicate PO (G4, G18).** `check_history` consults the
   case store and the Bravo export (`orders_for_po`).
    - `duplicate_po`: same revision, identical lines.
    - The same revision with different lines → `revised_po`, with the detail
      "nội dung đổi mà không tăng revision".
    - A revision with no base in either source → `revision_without_base`
      (today's code calls this `revised_po`).
    - Golden tests:
        - M04 → `correction_requested` → M07 ends with an upload file holding
          Rev.1's lines, and no M04 case left open;
        - processing M07 before M04 raises `revision_without_base`;
        - the Bravo-keyed re-send raises `duplicate_po`.

7. **Delivery date (G8).**
    - `requested_date_short_lt` counts from the received date
      (`received_at` in Asia/Ho_Chi_Minh), not the PO date. The lead time
      stays the standard one (`short_lead_time.lead_time: item_standard`):
      WIV-03-012 step 4 and the requirements doc's proposal (§3.2) both name
      the standard lead time. `quotation` remains an allowed value for when
      Proterial answers §4 item 9 otherwise, and the basis records the
      quotation's LT beside the standard one. The day basis comes from
      `short_lead_time.day_basis: calendar`.
    - Each line gets `suggested_delivery_date = max(requested_date,
received_date + LT)`, labelled as a suggestion.
    - Sales enters `confirmed_delivery_date` per line, prefilled from the
      suggestion.
    - A short-LT line needs `pc_confirmed_by/at` before `confirmed`.
    - No PC email draft (that is DW2).

8. **Message disposition (G9, G39, decision 10).** Add `MessageDisposition`
   and the reasons from the spec. `NotAnOrderError` becomes a disposition,
   not an exception the caller must remember to record.
    - For an internal sender, take the customer from the buyer the document
      names, by exact match, and raise `customer_unknown` until Sales
      confirms.
    - Raise `customer_temporary` for a temporary-code customer and
      `sender_unverified` from the message's auth results.
    - Route by sniffed bytes (`%PDF-`, an OOXML zip containing
      `xl/workbook.xml`), never by file name or the sender's media type.
      Refuse encrypted and macro-enabled files, and apply the byte, sheet,
      page and cell caps from policy (decision 13).
    - A test asserts exactly one disposition over every mock message.
    - A sample request is routed and carries the customer's export-control
      status.

9. **Completeness (G10).** Add `line_total_mismatch` and `value_uncertain`,
   and run both on every PO. `OrderCase.coverage()` returns lines printed,
   lines read, sheets/pages, checks × lines run and findings: the data behind
   "Đã đọc N/N dòng …".

10. **Currency and unit (G36).** Split `currency_mismatch` out of
    `_price_finding`, which folds currency into `price_mismatch` today. An
    unknown or different unit raises `uom_mismatch` on the line instead of
    failing the load.

11. **Check basis (G11, decision 11).** `OrderLine.check_basis` holds the
    convert entry or candidates; `quote_no`, price, currency, validity and
    copper basis; the LME month and value; MOQ, pack and LT with its source.
    `OrderCase` stamps `rules_version`, `parser_version`, `attachment_sha256`
    and `catalog_as_of`. Clean lines get a basis too, and a test asserts it.

12. **Export control (G35, part).** `missing_noc_esf` also fires when
    `denial_list_checked_on` is missing or older than
    `export_control.denial_list_max_age_days`. `export_control_mode: warn |
block_confirmation` is read by the `confirmed` transition.

13. **Process map (G21).** `dw_sales.domain.process.WIV_STEPS` maps each
    surveyed step to its states and artifacts. It is the one owner the
    overview reads.

14. **Policy (G15).** Amend `configs/policies/sales_order_rules@1.0.0.yaml`
    in place (it is not committed yet):
    - severities for every new code;
    - `short_lead_time` (`from: received_date`, `lead_time: item_standard`,
      `day_basis: calendar`);
    - `cross_check_required: true`;
    - `export_control_mode: warn` and `export_control.denial_list_max_age_days`;
    - `intake` caps;
    - `fiscal_year_start_month: 4`.

    Every value is fictional, and no key is added that nothing reads. This
    ticket reads only the platform layer. The tenant layer through
    `PolicyOverridePort` and `TenantOverlay` is ticket 12.

15. **Import contracts (G30), before the domain grows.** Show each one red
    with a deliberate import:
    - "Sales domain is pure": `dw_sales.domain` forbids fastapi, sqlalchemy,
      alembic, langgraph, langchain, qdrant_client, redis, httpx, boto3,
      minio, openai, anthropic, opentelemetry, openpyxl, pypdf and
      reportlab;
    - a layers contract: `presentation | adapters > workflows > application > domain`;
    - "Platform does not import contexts": `dw_kernel`, `dw_platform`,
      `dw_agent_runtime`, `dw_knowledge`, `dw_memory`, `dw_connectors`,
      `dw_observability` and `dw_evals` forbid `dw_sales`.

## Acceptance

- Unit tests per finding and per transition, driven by the mock messages and
  the follow-up fixtures (golden expectations).
- Negative tests, each refused:
    - the preparer cross-checks;
    - the Bravo recorder cross-checks;
    - a person whose hand-entered value is on the case cross-checks;
    - prepare with an open finding (other than `missing_noc_esf`);
    - confirm with `missing_noc_esf` open;
    - confirming a non-candidate code on a candidate line;
    - recording the Bravo entry without `bravo_entry_compared`;
    - confirm before `cross_checked`;
    - confirm with a short-LT line lacking a PC date;
    - an edit after `uploaded_to_bravo`.
- An edit in `prepared` returns the case to `in_review` with a new
  `case_version`.
- Error messages name ids, codes and fields, never an input value
  (spec decision 8).
- Instructions inside a PO body or cell never change a value (M12).
- Each import contract shown red with a deliberate import, then green.
