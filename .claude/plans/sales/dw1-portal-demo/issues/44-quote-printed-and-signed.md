# 44 — A quotation is printed and signed on paper; the signed copy may come back

Status: done (2026-10-28)
Blocked by: —
Category: enhancement

## Why

Đạt, 2026-10-28: no electronic signature. Proterial's survey has Q9 as "print
the quotation and get the head's signature"; FPT's deck of 13/10 promises
"trình duyệt", not "trình ký điện tử", and a plant without internet, which a
remote-signing service would need. So DW1 tells Sales the quotation is
approved, Sales downloads it to print and sign or sends it as it is, and the
signed copy may be uploaded back to be kept and sent; or Sales signs and sends
it themselves.

## Shape

- **Told on approval:** `CaseDecisions` delivers one in-app notification to
  whoever priced and submitted the quotation (the approver excluded), keyed
  `sales.quote.approved:<case>:<version>`, linking the quote page.
- **The signed copy** (`QuoteCase.signed_copy`, `SignedCopy`): uploaded at
  `approved`, `sent` or `master_list_recorded`; the status stays, the case
  version moves; a later upload replaces it. `POST /quotes/{id}/signed-copy`
  (base64, scope before key): `sales.quote.prepare` and `sales.price.read`
  (it carries prices), at most 10 MB, a PDF, JPG or PNG by its bytes, and the
  malware scan, which refuses when the scanner cannot answer. Stored as the
  artifact kind `quote_signed` (template `upload@1.0.0`), audited
  `sales.artifact.uploaded` and `sales.quote.signed_copy_attached`.
- **An upload-only kind:** `ArtifactGate.compose` None; never offered or
  rendered; `kept` keeps it downloadable after the case moves on.
- **The send draft** drawn after an upload attaches the signed copy instead of
  the unsigned PDF, beside the xlsx.
- **Web:** "Gửi báo giá cho khách" on the quote page from `approved`: the final
  document to download or open to print, the signed copy to upload (with the
  reason in words when the viewer lacks a scope), and where to draft or send.

## Not done

- DW1 sends no mail: Sales sends the draft from their own mailbox (no M365).
- Who signs, a company seal, and whether a signed copy must be kept: asked in
  the customer questionnaire (questions 21–26).
