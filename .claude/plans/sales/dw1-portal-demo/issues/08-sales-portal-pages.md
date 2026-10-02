# 08 — Sales portal pages

Status: ready-for-agent
Blocked by: 05, 06, 07

## What

- Tổng quan quy trình: steps of WIV-03-012 / WIV-03-023 with counts per state.
- Hộp thư (mock): list, "DW xử lý" per message or all.
- Đơn hàng: list; detail with source view (cells/lines highlighted) beside
  extracted lines, mapping, findings; actions Duyệt / Yêu cầu khách sửa /
  Từ chối; "Xác nhận" disabled until the source loaded; downloads.
- Báo giá: list; detail with request, Design reply, price evidence, decided
  price input, approval, downloads.
- Dữ liệu giả lập: read-only view of the mock master data.

## Acceptance

- `.claude/rules/ui-quality.md` checklist applied; Playwright walk-through of
  one order and one quotation with screenshots.
