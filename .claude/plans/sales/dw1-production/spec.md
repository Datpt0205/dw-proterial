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

## What the second batch of screens adds (11-10, 37 photos)

Bravo 8, module "Quản lý bán hàng", signed in as `SALEAI`. Sizes seen:
49,155 sales orders, 12,974 items, 347,029 customer-order-information rows.

**Bravo already owns every master list DW1 imports today.** Under "Danh mục":
Quy trình bán hàng, LME, đối tượng (customers and suppliers), vật tư hàng hóa
(items), Converting customer to PRV item, Base price, Master list of Export
code, vùng địa bàn, Delivery term, Delivery mode, Destination, Color code,
Forwarder, Black list, Invoice Separation, category, Sales special notice.
In production DW1 reads each of them from Bravo (ticket 14). It does not
keep a second copy that someone has to import (failure-modes #2).

| Bravo list | What it holds | DW1's use |
| --- | --- | --- |
| Đối tượng | groups 01 Direct, 02 Temporary (`TEMPSALES`), 03 Indirect, Maker, Supplier, potential supplier (approved by "Duyệt nhà cung cấp tiềm năng"); code (`FG…`, `TDC…`), name, second and short name, HMGM and TDC codes, address, type, tax code, payment terms; tabs for contracts, ECP tracking, invoices, debts, SOs, POs | the customer, payment terms; a `TDC…` code is a customer not yet official |
| Vật tư hàng hóa | groups Thành phẩm CA/EPB/HC/MR/OF and materials; code by family (`9000…` cable assembly, `2000…` hook-up wire, `7600…` magnet roll, `1000…` copper wire); tabs **Mô tả của khách hàng** (customer code → customer item codes, several per PRV code), **Tồn tức thời** (stock by warehouse), **Đơn hàng bán** (every SO of the item), Phát sinh bán hàng (invoices) | the PRV code and unit; "never produced" = no SO in the item's history; stock from Tồn tức thời |
| Converting customer to PRV item | input date, PRV code and name, specification, direct customer, converting description (colour written out: `HKV 0.30(12/0.18) TA WHITE`), invoice description, all-customer code and description, remark, id; approval states (only "3. Đã duyệt" seen) with "Duyệt Convert Master List" | **this is the convert list**: DW1 reads the approved rows (ticket 04) |
| Base price | BP date, BP code (`BP003874`: `BP` + 6 digits), short description, BP unit (km), convert rate (1,000 to m), STD unit, spec, category (CB, HK, SW, CA…), Cu weight kg/BP unit, base price USD/BP unit, lead time (weeks), MOQ, LME of BP (7,750), %MR of BP, material, variable and fixed cost, LT-MOQ notice, remark, scope; history of changes | the BP code Design answers is checked here (ticket 11) |
| LME | month, LME actual, LME center, who entered it | the LME center the price band reads; all seven months seen fit `floor(actual / 500) × 500 + 250` (12,891.38 → 12,750; 14,532.48 → 14,750), to confirm with Sales |
| Export code | item, export code (`ACA0001`), HS code, VN description, unit weight and length, carton size and weight, packing, coil/box, voltage, design sheet, valid and expiry dates | shipping and customs, not DW1 |
| Black list | input and effective dates, full name, key word, class (Customer, Maker, Vessel), reason | a customer on it holds the order (the hold DW1 has) |
| Export control program | ECP number (`ECP25-022`), direct and indirect customer, effective and terminated dates (fiscal year 01/04–31/03), country, product, application | **the ESF in Bravo**: an order is clear when an ECP covers its direct and indirect customer on the PO date |

**Quotations are already in Bravo.** "Báo giá, chào hàng" (made 30/10/26) has
the customer, the indirect customer, currency and rate, **LME from 7,500 to
15,000**, destination, payment terms (ADV, AMS30, AMS60), a "Duyệt" button,
and lines with customer, short and design description, specification, Cu
weight, LME at base price (7,750), base price, lot, MOQ and **price at fixed
LME**. "Master list báo giá" joins three blocks per row:
- the request (received and requested dates, customer description,
  end-user or project, consumption in km, application, MP, HCV check,
  status);
- the base price at quotation time (BP, LME, BP date, category, lead time,
  Cu weight, MOQ, material rate);
- the quotation (quote no. such as `QN-PRV-250410-00` or
  `QV-PRCH-2503-405`, dates, validity, expiry notice, class New/Update,
  delivery term/mode/destination, direct customer, **group customer** PRV,
  PRV(O), PCS, PRCH, PRK, PRAP, customer PIC, indirect customer, MOQ, unit,
  Cu weight, **center price**, LME, currency, rate, remarks, New/Revise/
  Cancel).

Center price equals the base price where LME is 7,750 in most rows. That
points to this rule: the price is fixed at the LME center, and an LME band
moves it. The formula is not on any screen (ADR 0008, Q-B8).

**The order grid ("Edit detailSO all", Layout1)** is the paste target.
Columns:
- PO line, PO number, item code, item description, base price name,
  specification, design number;
- other information 1–4, used as:
  1. the customer's line reference (`PTR/26/11/096-1`, `11TG5HA`);
  2. a second reference (`LJ18438`);
  3. (empty in every row seen);
  4. the end customer (`KOKUSAI ELECTRIC`);
- invoice separation (`CA`, the item's product group);
- quantity, unit (m, Pcs), price (5 decimals), amount, currency, USD rate,
  price in USD, total in USD;
- delivery date, sales counting date, status of delivery, delivery term;
- then the shipping columns (booking, BL, customs declaration, C/O,
  consignee, notify party, delivery to), which belong to shipping, not DW1.

Checks code can make on every row, all of which hold on the rows seen:
- amount = quantity × price, rounded half up to 2 decimals
  (6,100 × 0.02203 = 134.38);
- for VND, price in USD = price ÷ rate (101,533 ÷ 25,972 = 3.90933);
- total in USD = price in USD × quantity.

A PO of 15 lines is 15 rows under one SO. POs 261109-010 to -016 are seven
SOs with the same seven items each.

**After the SO:**
- "Create CDO" makes the row in "Customer order information (SP)": invoice
  number (`FBHP2611-008`), "Create IV", customs code, ETD, ETA, forwarder,
  booking. That is shipping and invoicing, the later "Giao hàng & CDO" DW,
  not DW1 (Q-B1 answered as far as the screens go).
- G-Samit is the group's reporting system. Bravo's reports send it SO data,
  sales data and the SO balance (Q-B2: DW does not need it).

Reports Bravo has that DW1 must not duplicate: Decline List, RFQ List,
Booking of new items, Order history, Sales and booking summarization, Report
of backlog, Shipment schedule, Exchange rate report, Sales daily report,
Booking report, new-item lead time.

**Third batch (11-10): the sales process, the YCBG and colour codes.** An
earlier note here called these screens empty. They are not: they had not
been photographed yet. The convert list's states 1 and 2 (before approval)
held no rows on 11-10. **An empty screen is a step with no data at that
moment, never a step that does not exist** (Đạt, 11-10). So a mapping still
goes through Bravo's states 1 → 2 → 3 (approved), and DW1 reads all three.

- **Quy trình bán hàng** is a diagram of Bravo's own process:
  - start → customer management (fed by the sales contract and the ECP)
    → customer asks for a product (fed by the forecast) → quotation;
  - → order recorded, or a sample order → delivery order → invoice and
    packing list (commercial or not) → shipping instruction → debit or
    credit note (fed by customer complaints) → end.

  DW1 covers the request, the quotation and the order recorded. Customer
  management with the ECP is the pre-sales and export-control part
  (tickets 15, 08). The rest is the later delivery DW.
- **Phiếu yêu cầu báo giá** is the YCBG in Bravo.
  - Number `RFQ` + yymmdd + `-` + nnn (`RFQ261110-002`). The description
    is usually the customer's mail subject (`HEV-[!]RFQ HEV26-2237 PRV
    HEV-2026-399 ASTI CORPORATION`, `KNT-[!]Re: 見積り依頼`).
  - The person who made it, a status (PENDING), Duyệt and Đánh lại số.
  - Lines: received date, RFQ no., direct and indirect customer, customer
    item description, **Design Check**, status.

  DW1's model (the Bravo YCBG number, Design's reply matched by it) holds.
  Ticket 16 now covers Bravo's real shape.
- **Color code** holds six rows only: S001 GR/YE (2 stripes/1 base, "Green/
  2Yellow or Yellow/2Green"), S002 EX (not G/Y), S003–S006 empty. Ordinary
  colours (WHITE, BLACK…) are written in the convert list's descriptions.
  The rule that puts a colour into a PRV code is asked (Q-B12).

## Before the RFQ: pre-sales (whiteboard, 11-10)

Drawn by Proterial and discussed as a step before DW1's RFQ lane. Read as:
- **Customers:** TDC (prospect) → direct (PRV, PRV(O)) or indirect through
  the group (PRHK, PRAP, PRCH) → official.
- **Pre-sales, in a circle:** new customer, approach, send (company profile,
  catalogue), verify.
  - It is linked to Design (new product).
  - It ends in a **new customer code in Bravo** (marked "A").
  - A "Form?" sits beside it.
- **Left side:** the RFQ form gives Design its needs ("DS need"), then the
  Base Price quote, numbered `RFQ2611…`. "SPA" and a circled `BP 01234`
  marked "AI", and "20% →".
- **Right side:** Sales, PO and PR, forms, a list.
- **Bottom:** SI (shipping instruction).

What DW can do there is in ticket 15. It is outside the contract's two
procedures, so it waits on Đạt (needs-triage).

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
| all | master lists | read from Bravo, not imported | 14 |
| before 1a | new customer | introduce, RFQ form complete, verify, code request | 15 (triage) |
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
- **DW reproduces the outcome of Sales' Excel work, not its steps** (11-10).
  Sales today goes from a PO (Excel, PDF) through the conversion workbook
  (B43) and the "in put PO" check (B42) to the SalesOrder paste sheet
  (B41). DW reads the PO itself, applies the workbook's rules as code and
  master data (ticket 04), and turns its TRUE/FALSE column into findings
  (ticket 03). The only Excel DW makes is the last one, the sheet pasted
  into Bravo (ticket 02), until the API takes writes. The workbooks are
  needed to learn the rules and as a check: DW's result on past POs must
  equal what the workbooks produced (B01/B02).
- **One rule source, not one per person** (11-10). Each Sales PIC may
  convert differently. DW follows three sources only:
  - Bravo's approved convert list (mappings);
  - one shared rule sheet that the Sales head signs off (B47), loaded as a
    tenant rule;
  - Sales' decision on the case.

  B48 (three full chains per PIC: PO → conversion workbook → SalesOrder →
  SO) shows where PICs differ; the head picks one rule per difference. A
  case no rule covers goes to a person, never to a guess. The person's
  decision can then be proposed as a rule through the rules editor, which
  needs a second person's approval.
- **Learning how they work without a transcript:** screen recordings (B50)
  are read frame by frame, as the 11-09 recording was. A written step
  sheet per person and process (B51) gives the why and the exceptions. The
  recording guide asks them to narrate in a self-recorded Teams meeting.
  Golden sets and UAT scenarios are in the forms workbook's own sheets
  ("Bộ kiểm thử (golden)", "Kịch bản UAT", B40, B53).

## Questions for Proterial (questions workbook rows 51–62, in this order)

- **Q-B1** What does "Create CDO" make, and who presses it after the SO?
- **Q-B2** "Sent to G-Samit": which system, sent by whom, and does DW need it?
- **Q-B3** "Returned": a returned order, or an SO sent back for correction?
- **Q-B4** Is `SALEAI` an account made for DW? DW needs an API key, not a
  client login.
- **Q-B5** Is "Duyệt" on the SO the cross-check DW1 records today, or a
  separate approval by the head?
- **Q-B6** Is one SO per PO always true, including a PO with many delivery
  dates and a PO revision?
- **Q-B7** Why does an item's SO history show each line as 990 + 10
  (SO2101-0002)?
- **Q-B8** How does a quotation's price move with the month's LME center
  (price at fixed LME 7,750, band 7,500–15,000, Cu weight, material rate)?
- **Q-B9** On the board: what are "SPA", "BP 01234 – AI" and "20% →", and
  which form is "Form?" beside the new Bravo code?
- **Q-B10** Quote numbers `QN-…` and `QV-…`: what tells them apart?
- **Q-B11** Does Design write its result in the YCBG's Design Check column in
  Bravo, or reply by mail? Who changes the status, and to what?
- **Q-B12** Where are the colour codes S001–S002 used, and is there a rule
  that puts an ordinary colour (WHITE, BLACK) into a PRV code?

## Tickets

`issues/01` … `issues/16`, in the order to build. Each names what it waits
on.
