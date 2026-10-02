# 06 — Artifacts: Bravo upload file and email drafts

Status: ready-for-agent
Blocked by: 04

## What

- Bravo sales-order upload xlsx (MOCK template, columns documented as such).
- Email drafts (.eml + preview text): PO confirmation, correction request,
  quotation send, decline, Design request. Rendered from templates; numbers
  come from the case, recipients from customer master data only.
- Stored under tenant/workspace keys; download route checks scope and tenant.

## Acceptance

- Generated files match the approved case values; download of another
  tenant's artifact is refused.
