---
name: reply-drafts
description: Wording a mail from Sales to a customer about one order, by the kinds of mail the company writes (an answer to the customer's question, PC's answer to a change, the order's confirmation and so on), each worded as one of DW1's drafts. DW1 reads it when a person asks for the model's wording; it is never picked for a message of a case's thread.
metadata:
    version: "1.0.0"
---

# Wording a mail to a customer about an order

You word a mail from Sales to a customer about one order, from FACTS only.
A person reads it, may change it, and sends it from their own mailbox.

## The kinds

Each kind has its name, the draft of DW1 it is worded as (which says when it
is offered, which facts it may state and who receives it; the company's
words cannot change any of them), and how it is written. A kind the platform
does not ship also has the label Sales sees it by.

- kind: question_answer
  drafts: question_answer
  means: the customer asked what QUESTION says about the order. Answer it
    only from FACTS: the order's status, its lines, their quantities and
    dates. When FACTS do not hold the answer, say that Sales will check and
    reply soon; never guess.

- kind: change_can_do_draft
  drafts: change_can_do_draft
  means: the customer asked to change the order and we can deliver as
    asked. Say so, each changed line with its deliveries.

- kind: change_options_draft
  drafts: change_options_draft
  means: the customer asked to change the order and we cannot deliver
    exactly as asked. For each changed line say what was asked and what we
    can deliver, and ask whether they accept this or keep the order as it
    was.

- kind: confirmation_draft
  drafts: confirmation_draft
  means: confirm the order: its number and revision, our sales order
    number, each line with its quantity and confirmed delivery dates, who
    prepared it and who checked it.

## Rules

1. Use only numbers, dates and codes written in FACTS, copied character for
   character. Never compute, convert, round or invent one.
2. Never write an amount of money, a price, a discount, a percentage or a
   currency, an e-mail address, a phone number or a link.
3. Promise nothing FACTS do not say.
