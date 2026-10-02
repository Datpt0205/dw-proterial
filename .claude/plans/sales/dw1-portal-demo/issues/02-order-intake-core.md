# 02 — Order intake core (deterministic)

Status: ready-for-agent
Blocked by: 01

## What

Domain + application, no framework imports:

- Classify a message (PO / revised PO / quote request / other) by code rules.
- Read Excel POs with openpyxl keeping `sheet!cell` anchors, including the
  one-sheet-per-page layout; read text PDFs keeping page/line anchors.
- Map customer codes: exact convert-list hit, else attribute candidates;
  never guess.
- Run every check in the spec's findings table.
- Order case state machine: received → checked → in_review →
  approved | correction_requested | rejected → uploaded_to_bravo → confirmed.

## Acceptance

- Unit tests per finding, driven by the mock emails (golden expectations).
- Instructions inside a PO body or cell never change a value (injection test).
