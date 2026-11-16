---
name: handoffs
description: Copying, out of a customer's email routed to Sales, what a hand-off to production control (PC) or quality assurance (QA) needs, by the kinds of hand-off the company writes (a delivery change, a complaint, a sample request and so on). DW1 reads it at one fixed step, after the mail is routed; it is never picked for a message of a case's thread.
metadata:
    version: "1.0.0"
---

# Pre-filling a hand-off to PC or QA

A customer's email has been routed to Sales as one of the kinds below. You
copy out of it the values the hand-off to PC or QA needs, character for
character. You write no sentence of your own: Sales reads the hand-off,
edits it and sends it from their own mailbox.

## The kinds

Each kind has its name (the kind of mail it is for), the fields it is copied
into (the company's words cannot add a field), the team it goes to (PC or QA;
the company's words cannot add a recipient) and what it means. A kind the
platform does not ship also has the label Sales sees it by.

- kind: delivery_change
  asks: order_lines
  to: pc
  means: the customer asks to change a delivery date or quantity of an
    order already placed. Copy the purchase order number and, for each line
    they ask to change, how they name the line (its number or the item
    code), the new quantity as written with its unit, and the new date as
    written.

- kind: complaint
  asks: lot_and_problem
  to: qa
  means: the customer reports a problem with goods delivered (a defect,
    damage, a shortage). Copy the purchase order number, the lot number, and
    one to three of the customer's sentences that describe the problem
    itself (never greetings, requests or what they want done).

- kind: sample_request
  asks: sample_items
  to: pc
  means: the customer asks for samples. Copy the description of each item
    they want as a sample, exactly as written, and the sample quantity as
    written.

## Rules

1. Copy only from the email, exactly as written. Never translate, reformat,
   complete or correct a value.
2. When a value is not in the email, leave it empty. A missing value costs
   nothing: a person fills it in. An invented one is sent to another team as
   if the customer had written it.
3. Never copy anything that says where to send goods, who to contact, an
   email address, a web address or a phone number.
