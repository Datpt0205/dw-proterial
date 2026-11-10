# 15 — Pre-sales before the RFQ: a new customer from approach to a Bravo code

Status: needs-triage
Blocked by: Đạt's call on scope (outside WIV-03-012 and WIV-03-023); Proterial's forms (RFQ form, new-customer form, company profile, catalogue)
Category: enhancement

## Why

At the survey on 11-10, Proterial drew a step before the RFQ on the
whiteboard. A new customer is approached, sent the company profile and
catalogue, given an RFQ form, and verified. Design is involved for a new
product, and the step ends in a new customer code in Bravo: a prospect
(TDC, Bravo's "Temporary customer") becoming official, direct or through a
group company.

## What DW can do (each ends with a person)

1. **Introduce:** draft the first mail in the customer's language from one
   example letter, with the profile and catalogue attached from a file
   library. Sales sends it. (Same door as every drafted mail, ADR 0006.)
2. **RFQ form complete for Design:** read the returned form (ticket 29's
   reader) and check the fields Design needs. Bravo's RFQ block has
   end-user or project, application, consumption (km), MP, specification.
   Draft a follow-up for what is missing.
3. **Verify:** check the name and its keywords against Bravo's black list
   and existing customers, and say which group company it would sit under.
   Code decides on a match; the model never does.
4. **New customer code:** draft the request with the fields Bravo's
   customer record needs (name, second and short name, address, tax code,
   type, payment terms, direct or indirect). A person creates it in Bravo,
   and DW reads it back (ticket 14).
5. **Nearest base price:** for the requested specification, propose the
   nearest existing BP codes from Bravo's list. Code parses the description
   (`UL2464 3x17AWG(50/0.18TA) LF`: standard, cores, AWG, strands). This
   reads the whiteboard's circled "BP 01234 – AI" as that; to confirm.

Not DW's: deciding to approach a customer, the price, creating the code in
Bravo.

## Open

- What "SPA" and "20% →" on the board mean (Q-B9).
- Whether this is in the contract's DW01 scope or a change request.

## Comments
