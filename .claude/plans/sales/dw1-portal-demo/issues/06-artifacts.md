# 06 — Artifacts: Bravo upload file, documents and email drafts

Status: done (2026-10-05, uncommitted)
Blocked by: 04, 05

## What

Each artifact is rendered from the case, never from a form value. Numbers
come from the case, and recipients come from customer master data only.
Each artifact records template `id@version`, `case_version` and sha256, which
the approval view shows. A download is the effect boundary: a person uploads
the xlsx or sends the `.eml`. So every download checks scope, tenant, its
state gate, and that the artifact's `case_version` equals the case's decided
version (409 otherwise). Price-bearing artifacts also need
`sales.price.read`. The route is in ticket 05's table.

| Artifact                                                                                                                                                    | Download allowed when                                          |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Bravo upload xlsx (MOCK template, documented as such)                                                                                                       | order `prepared` or later, and not returned                    |
| Cross-check sheet: per line PO value, anchor, upload value, finding, disposition, entered by hand by whom; the Bravo sales-order number and who recorded it | `uploaded_to_bravo`                                            |
| PO confirmation draft naming PIC and checker, confirmed date per line                                                                                       | `cross_checked`                                                |
| Portal-confirmation checklist (customer's `confirmation_channel = portal`)                                                                                  | `cross_checked`                                                |
| Correction request draft: exactly the `ask_customer` lines, each with PO value, expected value and source                                                   | `correction_requested`                                         |
| Change summary for Bravo plus a new confirmation draft                                                                                                      | `change_review` (confirmation: `cross_checked` again)          |
| Convert-list proposal xlsx (customer, customer code, PRV code, confirmed by, date)                                                                          | any line `candidate_confirmed`; nothing writes the list itself |
| "Cần Design tạo mã" hand-off note                                                                                                                           | a `code_unmapped` line with no candidate and no code typed yet |
| Cannot-supply draft                                                                                                                                         | `closed(cannot_supply)`                                        |
| YCBG draft (MOCK form)                                                                                                                                      | `ycbg_drafted` or later                                        |
| Design request draft                                                                                                                                        | `ycbg_recorded` or later                                       |
| Spec-discussion reply draft                                                                                                                                 | `spec_discussion`                                              |
| Decline draft with the reason                                                                                                                               | `declined`                                                     |
| Quotation document xlsx + PDF (MOCK form): preview                                                                                                          | `pending_approval`, for the pricer and approvers               |
| Quotation document, final, with approver and approval time; send draft attaching it and naming the spec no.                                                 | `approved` and the hash matches                                |
| Master-list update xlsx (MOCK columns)                                                                                                                      | `sent`                                                         |

## Amendments (2026-10-03)

- **Gates (G16).** As in the table. Land them before any artifact.
- **Language (G33).** Templates are keyed by `(kind, language)`, and a
  draft's language is `Customer.language` (vi, en, ja). A missing template
  refuses to render, with the reason. There is no silent fallback to another
  language.
- **Sender.** The `.eml` From is a policy key, defaulting to the deciding
  PIC's address until Proterial answers (requirements doc §3.1). Reply-To is
  the shared Sales address.
- **Versioned templates (G15).** `configs/copy/sales_emails@1.0.0.yaml` and
  `configs/policies/sales_bravo_upload@1.0.0.yaml`, both MOCK, are pinned by
  the release manifest. Proterial's wording arrives only as a tenant
  override (decision 14).
- **Formulas (G29).** Every customer-supplied string is written as text
  (`data_type 's'` / `quotePrefix`), never as a formula.
- **Storage (G29).** Keys are
  `{tenant_id}/{workspace_id}/sales/{case_id}/{artifact_id}` in the
  knowledge-artifacts bucket, so offboarding exports and purges them. Keys
  are generated by the server.
- **PDF writer (G38).** The quotation PDF needs a writer. Either `apps/docgen`
  renders it from the xlsx, or reportlab stays a runtime dependency. Decide
  in this ticket and record it; until then the move of reportlab to the dev
  group is on hold.
- No PC email (DW2). The NOEC request draft is ticket 12.

## Acceptance

- Generated files match the decided case values, and the quotation document
  carries no other customer's price, evidence or management instruction.
- Per artifact kind, two negative tests: a download before its state, and a
  download after an edit that bumped `case_version`. A download of another
  tenant's artifact is refused.
- The fixture description starting with `=` lands as a text cell.
- Per language a render test, including M10 (ja). A missing (kind, language)
  is refused.

## As built (2026-10-05)

Code: `dw_sales.application` (`artifact_content.py` the content model, writer
port and copy models; `drafting.py` what a composer is handed;
`order_artifacts.py` and `quote_artifacts.py` one composer per kind;
`artifacts_service.py` the gate table, render, list and download),
`dw_sales.adapters.artifact_files` (openpyxl, reportlab, `email`),
`dw_sales.adapters.policy_files.load_artifact_copy`, wired at
`dw_api.bootstrap.wiring.build_sales`. Versioned and pinned by the release
manifest: `configs/copy/sales_emails@1.0.0.yaml`,
`configs/copy/sales_documents@1.0.0.yaml`,
`configs/policies/sales_bravo_upload@1.0.0.yaml`, all MOCK. Tests:
`dw_sales/tests/unit/test_artifacts.py` (per kind: rendered at its state,
refused before it, refused after an edit bumped the version; contents, leak,
languages), `test_artifact_files.py` (text cells, determinism, drafts),
`test_service_scopes.py`, `test_sales_isolation.py` (listing under RLS) and
`apps/api/tests/integration/test_sales_api_artifacts.py`.

Decisions taken here, beyond the table:

- **Rendering is a step of its own.** `POST /orders|quotes/{id}/artifacts
{kind, case_version}` renders a kind from the case at the version the caller
  saw: `sales.case.read` plus the context's write scope
  (`sales.order.prepare` / `sales.quote.prepare`), `sales.price.read` for a
  price-bearing kind, the gate, and the current version (409 otherwise). Done
  again at the same version it answers what is stored. `GET .../artifacts`
  lists every record (template, case version, sha256, whether this caller may
  download it now) and the kinds `available` to this caller. The OpenAPI
  snapshot was regenerated; the TypeScript client was not (ticket 08's).
- **"The decided version" is the case's current version.** Every decision
  bumps it, so an artifact rendered before the latest one answers 409
  (`reason: stale_artifact`) and is rendered again; the bytes served are the
  ones whose sha256 the record holds (503 otherwise).
- **Two gates changed from the table.** The confirmation draft and the portal
  checklist open at `confirmed`, not `cross_checked`: the confirmed date per
  line is entered with the confirmation (ticket 05), so a draft at
  `cross_checked` could not carry it. The Bravo upload file is not offered in
  `change_review`: a revision of an order in Bravo is applied there from the
  change summary, and a new upload file would key the order twice. The
  "Cần Design tạo mã" note needs a `code_unmapped` line with no candidates.
- **Copy is two files, not one:** the drafts' words (`sales_emails`) and the
  sheets' and the quotation's (`sales_documents`). An artifact records
  `<copy_id>.<kind>.<language>@<version>` (or `sales_bravo_upload@1.0.0`). A
  draft to the customer is in `Customer.language`; internal sheets and notes
  to Design are Vietnamese. A missing `(kind, language)`, label, word or value
  refuses to render with the reason (`template_missing`, ...).
- **Sender.** `sales_emails.sender.from` is `drafting_pic` (the PIC who
  renders the draft and sends it from their own mailbox; their directory
  email, refused when they have none) or `shared_sales`; Reply-To is the
  shared address `sales@seller.example`. Recipients are master data's only:
  the customer's contacts, the submitted document's recipients for a
  quotation, `sales_quote_rules.design_mailboxes` for Design.
- **PDF writer (G38): reportlab stays a runtime dependency of dw_sales.** The
  quotation PDF is printed from the same content as its xlsx, not converted
  from it; `apps/docgen` is not involved. Japanese uses Adobe's CID font (no
  file shipped); a Vietnamese name inside it falls back to the DejaVu
  Latin/Vietnamese subset the mock attachments use. The hold on moving
  reportlab to the dev group is lifted: it stays.
- **The quotation is bound to the approval.** It is written from the
  submitted `CustomerQuoteDocument` alone and prints its data hash (the one
  the approval names); the final names the approver and the approval time,
  and is refused unless the approval's hash is the document's. Files are
  stamped with the submission or approval time, not the clock, so the send
  draft attaches the final xlsx and PDF byte for byte as stored.
- **Formulas (G29).** Every string cell is type `s`; one that starts with
  `= + - @`, a tab or a carriage return also carries the quote prefix. PDF
  text is escaped; a draft's headers refuse a line break.
- **Audit.** `sales.artifact.rendered` and `sales.artifact.downloaded`, in the
  same transaction as the record, with ids, kind, template, case version and
  sha256; never an amount. No case event (nothing moves the case).
- **Downloads** answer `Cache-Control: no-store` and `nosniff`; the file name
  is kind, case id and extension, never a value from the file.

Open:

- A `value_uncertain` correction carries one typed value for a whole flagged
  region, not per field, so the upload file carries the values as read and
  the cross-check sheet shows the typed value and who typed it beside them.
  Binding a typed value to one field is a domain change (ticket 02 follow-up).
- The object is written before the record commits: a failed commit leaves an
  object under the tenant's prefix with no record (offboarding purges it;
  retention is ticket 12). Two simultaneous renders of one kind and version
  both store; a unique index would need a migration.
- Rendering is not refused while DW1 is paused (the pause stops processing).
  Đạt to decide whether drafting is DW1's work for the stop control.
- A person named on a case who has left the workspace refuses the render
  (fail closed), which also blocks re-rendering an old case's drafts.
