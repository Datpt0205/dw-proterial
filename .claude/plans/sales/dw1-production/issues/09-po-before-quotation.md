# 09 — A PO for an item with no valid quotation opens a quote case

Status: ready-for-agent
Blocked by: none
Category: enhancement

## Why

Drawio 2a: a PO can arrive before any quotation, and Sales then quotes
first. DW1 flags the line (no quotation) and stops there.

## Shape

- From that finding, "Mở báo giá" opens a quote case for the customer and
  the items, linked to the order case. The order waits on it and resumes
  when the quotation is approved.

## Acceptance

1. The order cannot be prepared while its linked quote is open.
2. Approving the quote clears the finding at the order's next check.

## Comments
