# 58 — Quotation type and signature, and facts read from Bravo instead of told in chat

Status: needs-triage
Blocked by: 50 (reads from Bravo), 52 (which columns "Duyệt" changes)
Category: enhancement

## Why

The BA answered on 2026-11-20 (Long Đình Bảo, in chat with Đạt):

- **Signatures.** QN needs no signature; QM and QS are signed as usual.
- **Choosing the type** depends on two questions: is the item in the item
  master, and is it a special item. QS items are in the item master, marked
  as special.
- **TDC → FG.** When a TDC customer first trades, the accountant replaces the
  code with an FG code on the same customer record, and the TDC code moves to
  another column. Old quotations are not expected. If the price has changed,
  the customer is told the price was updated and is sent a new quotation.

DW never signs. Đạt asked how the signed copy comes back. He sees two ways,
the PIC telling the chat or DW polling Bravo, and finds the chat riskier.

## Shape

- **Type.**
  - Not in the item master → QN.
  - In the master, not special → QM.
  - In the master and special → QS.
  - This reading still needs the BA's confirmation, and we need to know which
    field marks a special item. The survey found no such field:
    `SpecificItems` is Bravo's Color code list.
  - Bravo does not classify; the type is chosen when the quotation is entered.
    DW proposes the type and the PIC confirms.
- **Signature (QM, QS).**
  - Once the quotation is entered and approved in Bravo, DW renders the PDF
    from the Bravo record, so the content is Bravo's. The signer signs or
    stamps it.
  - Primary path: the PIC sends the signed copy to the customer in the RFQ
    thread. DW sees the outgoing mail with its attachment in the monitored
    mailbox and closes the step. Nothing is parsed from chat.
  - Alternative: the PIC uploads the scan to the case. DW reads its quotation
    number and total and compares them with Bravo, warns on a mismatch, then
    drafts the mail with the file for the PIC to send.
- **Facts held in Bravo are polled, never taken from chat words.**
  - This covers approval ("Duyệt"; ticket 52 measures which columns change),
    Design done (`Status = 'CLOSE'`), the SO number, and dates a person edited
    in Bravo.
  - Reads come through ticket 50's sync every 5–15 minutes.
  - Chat carries only what exists in a person's head: decisions and
    exceptions (ticket 56).
- **TDC → FG.**
  - DW looks quotations up by the FG code. It also looks them up by the old
    TDC code (likely `B20Customer.SalesTempCode`, to confirm) for history.
  - A changed price leads to a drafted "price updated" mail with the new
    quotation, for the PIC to send.

Checked in Bravo's code on 11-20:

- The customer screen labels `B20Customer.SalesTempCode` "TDC code", so the
  old TDC code lives there. Confirmed.
- The quotation's type is the header field `TypeCustomer` ("Quotation type"),
  picked from `B20Class` where `ParentCode = 'TypeCustomer'`; it drives the
  number (`ufn_B30BizDoc_DefaultDocNo_QS`).
- A separate header field `ClassCode3` ("Báo giá đặc biệt") picks from
  `B20Class` where `ParentCode = 'SQSepcial'`.
- No item-master flag for "special" was found.
- `docs/proterial/sql/05-chot-cac-diem-con-treo.sql` (one run, read-only)
  counts the quotations and items per type, to settle the QN/QM/QS mapping and
  the special marker from data.

## Acceptance

1. Each type comes out right for one item per case, on UAT data.
2. A signed quotation sent from the mailbox closes the step without anyone
   writing in the chat.
3. An approval made in Bravo moves the case within one sync interval.

## Comments
