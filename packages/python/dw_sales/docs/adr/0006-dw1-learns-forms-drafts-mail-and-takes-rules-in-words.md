---
status: Accepted
date: 2026-10-29
accepted: 2026-10-29 (Đạt, choosing each recommended option)
amends: ADR 0005 (what a model may produce), ticket 30 (a second person approves a layout)
---

# DW1 learns a PO form, drafts customer mail from an example, and takes a rule change in words

## Context

Đạt, 2026-10-29: "đang cần config các mẫu PO rồi email khá là phức tạp, nếu
giảm được chuyển cho AI làm thì làm đi rồi bỏ các config rườm rà đó đi, về mẫu
email gửi khách thì để lại phần ví dụ ... nó quá rườm rà để 1 người non tech
có thể config". Three things a person configures today read as engineering
work to the people who would do it:

- **A PO form** needs a layout a person maps (or confirms a model's pre-fill)
  and a second person approves (ticket 30) before DW1 reads a customer's POs.
- **Customer mail** is a template per kind and language with `${value}` slots
  (`sales_emails`, 380 lines over three languages).
- **Rules** are versioned documents (`sales_kpi@1.0.0`) a person edits field by
  field, with version numbers and platform/tenant layers on the page.

The model is about to be replaced with a larger one, on the plant's server.
ADR 0005's reason to keep a model narrow still holds whatever its size: a
customer's mail is untrusted input, and money and outbound effects need an
accountable person. What changes here is where that line sits.

## Decision

Asked as three questions; Đạt chose the recommended option of each.

### 1. DW1 learns a customer's PO form

When no layout reads a PO, DW1 asks the model for one (the pre-fill of
ticket 30). If **every** check `LayoutChecks` runs passes (each label one cell,
the titles on one row, each column plausible, the reader end to end with a
total and no `line_total_mismatch`), DW1 **adopts** it as the customer's
layout itself and reads the PO with it in the same run. Nobody approves it.

- The layout is stamped as learned (`origin = 'model'`, proposed by DW1's
  actor, no approval row) and audited `sales.layout.learned` in the same
  transaction; a person's own mapping keeps ticket 30's maker and checker.
- The first `layout_onboarding.uncertain_first_pos` POs read through a learned
  layout still flag every value `new_layout`, so Sales confirms what it read
  beside the source, exactly as for an approved one.
- A proposal any check refuses is not adopted: the message goes to Sales as
  today, and the onboarding screen stays reachable from that message, not
  from the menu.
- Every PO read through any layout is still checked line by line and against
  its total; a learned layout that reads a later PO wrongly raises findings
  like any other.

### 2. Customer mail is drafted from an example

Each kind of mail keeps one **example letter**, plain text a person writes
like any letter. DW1 drafts each mail in the customer's language following
the example's tone and order; **code** writes the subject and every fact
(numbers, dates, codes, names of items, prices) into a block it renders
itself. The model writes only the prose around that block, and code refuses
prose that holds a digit or does not hold the block's slot exactly once. A
refused or missing draft falls back to today's template. Sales reviews every
draft before it is sent, as today. This amends ADR 0005's "customer-facing
prose stays human" to "customer-facing prose is drafted by a model and sent by
a person".

### 3. A rule is changed in words

Each rule shows what it does in sentences code writes from its document, not
its version string. To change one, a person types what they want ("nhắc
khách sau 3 ngày thôi"); the model proposes the whole new document for that
rule, which is validated against the rule's schema like any version; the page
shows before and after as sentences, and the person applies it through the
existing door (the head's version applies at once; the admin's waits for the
head). The model proposes, it never applies. Rules that read as engineering
(the Bravo upload format, document wording, KPI baselines) move under
"Nâng cao", shown to the admin only.

## Consequences

- Onboarding a customer stops being a task: the first PO is read without one.
  The cost is that a wrong layout passing every check is adopted unseen; the
  `new_layout` flag on its first POs and the per-PO total are what catch it.
- `sales.po_layouts` takes rows with no approval (`origin = 'model'`), and its
  constraints say which rows may be so.
- A mail's wording can now differ between two drafts of the same kind; its
  facts cannot, because code writes them.
- A model step remains measured before it is trusted (ADR 0005 §9): the
  learned layout rides on `layout_proposal`'s bar, and the two new steps get
  their own datasets and bars before their switches do anything.

## Addendum, 2026-10-29: a sender is learned the same way (the AI list, item 5)

A mail from an address on no customer's domain was `customer_unknown` for
every mail from it until the master data changed. Now the model reads which
customer wrote it, from candidates code picks (a word of a customer's name no
other customer's name holds, found in the mail), and code accepts only a
candidate whose words, quoted from the mail, hold such a word. A person
confirms; the sender's **address** is then kept as the customer's
(`sales.recorded_customer_senders`) and the mail processed again. The
address, not the domain: a buyer writing from a public mail provider must not
make every sender there that customer's. The customer's own domains answer
first. As with the convert list, the confirmation is the person's decision
and no head's batch review follows (Đạt, 2026-10-29).
