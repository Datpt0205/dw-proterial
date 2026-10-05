# 08 — Sales portal pages

Status: ready-for-agent
Blocked by: 05, 06, 07, 11

## What

- **Việc cần làm** (`/sales` home, G22), oldest first, with age and deadline
  (`quote_due`; the requested date of a short-LT line). It lists:
    - orders awaiting the caller's preparation (assigned to the caller, or
      unassigned);
    - orders awaiting cross-check where `prepared_by ≠ me`, with the waiting
      time;
    - findings awaiting a disposition;
    - quotes awaiting pricing, or the caller's approval where
      `priced_by ≠ me`;
    - YCBGs overdue at Design;
    - messages routed to Sales.
- **Tổng quan quy trình.** A KPI strip labelled "trên bộ mẫu giả lập", then
  counts per WIV step. The page renders what the API returns and holds no
  second step table. It also shows "Email chưa có hướng xử lý: N".
- **Hộp thư (mock):** class, disposition, reason and owner per message; "DW
  xử lý" per message or for all.
- **Đơn hàng:**
    - the list;
    - the detail: the source beside the extracted lines, with boxes drawn on
      the rendered page or cells marked on the sheet grid, never on
      extracted text;
    - the coverage statement ("Đã đọc N/N dòng trên S sheet/trang; tổng khớp
      ô TOTAL; K kiểm tra × N dòng; F cờ");
    - each line's basis ("Đối chiếu với báo giá Qxx (hiệu lực dd/mm–dd/mm),
      LME tháng mm/yyyy; dữ liệu đến ngày dd/mm");
    - a "Có phiếu mới hơn" banner on a superseded revision.
- **Per-finding controls (G3):** Chấp nhận + lý do / Sửa giá trị / Yêu cầu
  khách sửa, offered only where the code allows, and no "chấp nhận tất cả".
- **Candidate picker (G13):** each attribute as PO value | item value |
  khớp/lệch.
- **Date column (G8):** "gợi ý" kept distinct from "đã xác nhận".
- **Order actions:** Chuẩn bị xong, Đã nhập Bravo (số đơn, and the PIC's
  statement that the Bravo entry was compared with the PO), Kiểm chéo,
  Trả lại, Đã gửi xác nhận, Đóng hồ sơ (lý do). A disabled action states
  why, in words. Examples:
    - "Còn 2 cờ chưa quyết định";
    - "Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (tách nhiệm,
      WIV-03-012 bước 9)";
    - "Chưa mở nguồn".
- **Báo giá:**
    - the list sorted by `quote_due`, showing time left in giờ Việt Nam, with
      overdue as its own group;
    - "YCBG chờ Design" with the days waiting;
    - the detail: request, Design reply, the evidence (other customers' rows
      show "Đã ẩn" with a lock unless the caller holds the scope), quotation
      findings, the decided-price input, and the document preview beside the
      approval;
    - actions: Đã lập YCBG (số phiếu), Gửi Design, Gửi KH thảo luận spec,
      Từ chối báo giá (lý do), Trả lại định giá, Đã gửi KH, Xác nhận master
      list.
- **Rà soát báo giá năm:** the screening report.
- **Dữ liệu giả lập:** a read-only view of the mock master data, with prices
  per the price scopes.
- The Sales header shows DW1's paused state, who paused it and when. A draft
  shows its language.

## Per role (the product's UI brief)

| Persona / role                      | Sees                                      | Hidden or disabled                                                         |
| ----------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------- |
| An — `sales_pic` + export control   | Everything above; amounts                 | Other customers' prices "Đã ẩn"; Kiểm chéo on his own orders; Tiếp tục DW1 |
| Diệu — `sales_pic` + price evidence | As An, plus other customers' prices       | Duyệt báo giá (no scope); Kiểm chéo on her own orders                      |
| Giang — `sales_head`                | Everything; Duyệt báo giá; Tiếp tục DW1   | Duyệt on a quote he priced, with the reason                                |
| Khoa — `sales_pic` + deputy         | As a PIC, plus Duyệt báo giá              | Duyệt on a quote he priced                                                 |
| Hà — `sales_viewer`                 | Tổng quan quy trình only, without amounts | Every other Sales nav item absent; direct URLs show the 403 state          |
| Bình, Tâm — no `sales.*`            | No Sales nav                              | —                                                                          |

## Amendments (2026-10-03)

- Nav items are keyed to `sales.overview.read` / `sales.case.read`, not
  `sales.read`. Role labels come from `platform.roles.name`, and
  `apps/web/lib/nav/roles.ts`'s second label map goes (G2, G38).
- Icons come from `@ant-design/icons`, replacing lucide-react in the Sales
  nav. `sonner` is dropped when the first Sales page lands (G38).
- `lib/money.ts` takes `Currency` from the generated client and adds JPY,
  with a test that iterates the enum (G38).
- Virtualise the lines table past about 200 rows, and record Sales decision
  time per order (G23).

## Design reference (2026-10-05)

The visual language comes from Đạt's E-HSDT v3 prototype, kept outside git
at `docs/design/ehsdt/design_handoff_ehsdt_v3/` (another product's handoff;
open with `npx serve prototype`). Same stack and rules (antd v6, top navbar,
`ui-quality.md`), so its components and patterns are reused; its screens are
re-cut to the Sales process, never copied with bidding terms.

| E-HSDT v3 screen                             | DW1 screen                                                             |
| -------------------------------------------- | ---------------------------------------------------------------------- |
| Shell (56 px top menu, role menu, bell)      | Same shell, Sales group                                                |
| V3Bids (package list)                        | Việc cần làm / Hộp thư (disposition, owner, age, due)                  |
| V3BidOverview (gate timeline)                | Order / quote case header: WIV step timeline and who acts next         |
| V3BidMatrix + V3Source (value on page image) | PO lines with source on the rendered page / sheet grid, coverage line  |
| V3BidFindings (findings, waive)              | Per-finding disposition (accept with reason / correct / ask customer)  |
| V3BidDrafts                                  | Upload file, confirmation, correction, YCBG, quotation, decline drafts |
| V3BidPricing + V3Price ("Đã ẩn")             | Quote pricing evidence; amounts hidden without the price scopes        |
| V3Approvals                                  | Cross-check queue and quotation approval (maker ≠ checker)             |
| V3Exec                                       | Overview KPI strip "trên bộ mẫu giả lập" (sales_viewer)                |
| V3Library / V3Vault                          | Dữ liệu giả lập: customers, items, convert list, quotations, LME       |
| V3Catalog, V3State, V3Tag, V3Btn, V3Field    | Shared states, label table from CONTEXT.md, buttons, fields            |

Not reused: sealing, post-bid, guarantees (D5), onboarding vault. Pending
E-HSDT variants (D07 palette etc.) are not decided here; DW1 takes the
default theme already in `@dw/ui`.

## Acceptance

- The `.claude/rules/ui-quality.md` checklist is applied.
- A Playwright walk-through follows the spec's "Done when" as the personas,
  with screenshots, including each persona's refusals. It never signs in as
  `platform_admin`.
