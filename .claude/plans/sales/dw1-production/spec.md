# DW1 in production — the surveyed flow on Proterial's own Bravo

Status: ready-for-agent where a ticket says so; the rest waits on Proterial's
forms (B41–B45) or on a decision below
Owner: Đạt
Started: 2026-11-10

## Why

`dw1-portal-demo` built DW1 end to end on mock data behind real ports
(tickets 01–45). The onsite survey (11-09) and Bravo's own screens (11-10)
show where the real process differs. This spec covers only that
difference, so the demo's tickets stay the record of what is already built.

Sources:

- the BA's flow `Downloads/proterial/prv.drawio`, 4 pages: 1a RFQ intake,
  1b pricing and sending, 2a PO intake to confirmation, 2b changes after
  confirmation;
- the 11-09 recording (frames read; speech waits on the Teams transcript,
  B44, else a local transcription);
- four photos of Bravo 8, "Đơn đặt hàng bán", taken 11-10 (Đạt);
- the forms list `docs/proterial/Danh-sach-bieu-mau-va-API-Bravo_DW1-DW2.xlsx`
  (outside git), B41–B45 in particular.

## What Bravo shows (11-10)

**Module "Quản lý bán hàng".** Menu: Hợp đồng bán, Export control program,
Phiếu yêu cầu báo giá (YCBG), Báo giá chào hàng, Đơn đặt hàng mẫu (free and
charged), Đơn đặt hàng bán, Đơn đặt hàng bán (Returned), Phiếu giao hàng
(Form 1 and 2), Khiếu nại của khách hàng, Forecast khách hàng. Shipping:
commercial and non-commercial invoices, shipping instruction, debit note,
phiếu cân. Master lists: customer, **báo giá**, lệnh sản xuất, free samples,
customer order information (SP, Form 1, Form 2), complaints, replacements,
**cancelled orders**, non-trade goods.

**Sales-order list.** Folders: all orders, orders being followed, closed
orders, my documents, by month, suspended. Toolbar: Mẫu in, **Duyệt**,
Đánh lại số. Rows are grouped by status ("Đã hoàn thiện"). Header columns:

| Bravo column | Seen | Meaning for DW1 |
| --- | --- | --- |
| PO No. | `240588001101`, `261109-010`, `VN-261109-2527`, `81260051` | the customer's PO number, in the customer's own format |
| SO order | `SO2611-000161` … `000176` | Bravo's number; `SO` + yymm + sequence |
| Input / Booking / Receipt date | 10/11, 10/11, 09/11 | receipt = the day the PO came in; booking = the day it was entered |
| KH trực tiếp / gián tiếp | `FG13100024`, `FG00010874` | direct and indirect customer codes |
| TotalQuantity, Tổng tiền, Tiền tệ, Tỷ giá | USD at rate 1.00; VND at 25,972 | **the books are kept in USD** |
| Create CDO | a button per row | unknown, asked (Q-B1) |
| Delivery mode / term / destination | ROAD·FCA·PRV, AIR·CIP·NARITA, ROAD·DAP·TEV | constant per customer in every row seen |
| Actual payment terms | "T/T at the end of following month", "AMS60", "AMS45" | constant per customer |
| Cán bộ nhân viên | three Sales PICs | the customer's PIC |
| Returned, Closed, Sent to G-Samit | button, two check boxes | asked (Q-B2, Q-B3) |

**Line tabs:** Chi tiết đơn hàng, Thay đổi chi tiết (change history),
Báo giá, Công việc, Phát sinh bán hàng, Duyệt chứng từ, Mẫu in tài liệu kinh
doanh. Line columns: Mã hàng (`7600000034`, the PRV code), name
("Magnet roll - 5C4460"), unit (Pcs), quantity (40.000), unit length (1.00),
quantity per box (40), box quantity (1.00), unit price (4.32850, five
decimals), amount (173.14), Ngày KH yêu cầu, Ngày XN giao hàng đầu tiên,
XN giao hàng, Sales Date. Below: "Chi tiết thực hiện" (document code,
number, date, unit, quantity): what was delivered against the line.

**What follows for DW1:**

1. One SO per customer PO in every row seen (16 POs, 16 SOs). DW1's
   `bravo_so_no` per order case matches.
2. Delivery mode, term, destination, payment terms and PIC come from the
   customer, not the PO: the paste sheet fills them from master data, and
   a PO that says otherwise is a finding, not a silent overwrite.
3. Code can check what Bravo computes: amount = quantity × price (price to
   5 decimals, amount to 2), box quantity = quantity ÷ quantity per box.
4. "Ngày XN giao hàng đầu tiên" vs "XN giao hàng" is the first confirmed
   date vs the current one: a PC re-confirmation changes the second and
   keeps the first. DW1's delivery schedule needs both.
5. "Chi tiết thực hiện" and the closed/followed folders are what a status
   question ("đã giao chưa") should read once the API exists.
6. The status bar names the signed-in user `SALEAI`: possibly an account
   made for DW. Asked (Q-B4); DW never signs in to Bravo's client either
   way (ADR 0026).

## Flow: who does each step in production

Pages of the drawio → what changes. "Built" means a demo ticket did it.

| Step | Today (person) | DW1 in production | Ticket |
| --- | --- | --- | --- |
| 1a RFQ arrives | reads mail or portal | reads it, opens a quote case (built) | — |
| 1a mass or pcs | Sales knows | proposes mass/pcs, pcs → request to JP & HQ drafted | 05 |
| 1a code unknown | asks Design | drafts the new-code request with the nearest PRV codes | 06 |
| 1a YCBG, Design reply | Bravo + mail | drafted, reply read (built); Base price and BP code kept | 11 |
| 1b price | Excel, LME band, margin, rate | suggested price, Sales decides, head approves | 13 (after ADR 0008) |
| 1b quotation sent | signed PDF, master list | printed and signed (built, 44); master list read from Bravo | 12 |
| 2a PO arrives | portal / mail | read, mapped, checked (built); PO before quotation opens one | 09 |
| 2a conversion | conversion workbook | its rules and colour codes as master data | 04 |
| 2a export hold | export-control PIC | hold (built); NOEC request drafted | 08 (triage) |
| 2a PC dates | mail to PC | request drafted, reminded, dates read (read: built) | 07 |
| 2a enter in Bravo | paste SalesOrder sheet | the sheet in Bravo's real layout; a person pastes | 02 |
| 2a check entry | "in put PO" TRUE/FALSE | DW reads the SO back and compares line by line | 03 |
| 2b changes | customer or internal | customer revision (built); internal changes and bulk splits | 10 |
| all | — | the model is Qwen3.8 on Strata | 01 |

**Out of scope:** logging in to customer portals and downloading from them;
the electronic stamp; anything typed into Bravo by DW.

## Boundaries that do not move

- DW never writes to Bravo. A person pastes the sheet and presses Bravo's
  own buttons; reads go through the vendor's API (ADR 0026).
- The model reads and drafts; code checks every value against its source
  and decides; a person approves and sends (dw_sales ADR 0005, 0006).
- Every layout, rule and template here is a tenant version of a policy,
  never an edit of the platform's file.

## Questions for Proterial (into the questions workbook)

- **Q-B1** What does "Create CDO" make, and who presses it after the SO?
- **Q-B2** "Sent to G-Samit": which system, sent by whom, and does DW need it?
- **Q-B3** "Returned": a returned order, or an SO sent back for correction?
- **Q-B4** Is `SALEAI` an account made for DW? DW needs an API key, not a
  client login.
- **Q-B5** Is "Duyệt" on the SO the cross-check DW1 records today, or a
  separate approval by the head?
- **Q-B6** Is one SO per PO always true, including a PO with many delivery
  dates and a PO revision?

## Tickets

`issues/01` … `issues/13`, in the order to build. Each names what it waits
on.
