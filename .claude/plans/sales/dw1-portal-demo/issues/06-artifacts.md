# 06 — Artifacts: Bravo upload file, documents and email drafts

Status: ready-for-agent
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
