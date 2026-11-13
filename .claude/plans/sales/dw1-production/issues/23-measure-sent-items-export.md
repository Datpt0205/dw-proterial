# 23 — Measure: does a sent mail's export keep its thread headers

Status: needs-info (a Microsoft 365 mailbox to try the flow on)
Blocked by: Đạt: a test M365 tenant or Proterial's, for one person's flow
Category: spike

## Why

dw_sales ADR 0009 decision 3: Sales' sent mail joins the thread. A `.msg`
saved from Sent Items (Box B03, B11) carries no `In-Reply-To`, `References`
or `Thread-Index`. Whether Power Automate's "Export email (V2)" of a sent
item keeps them decides how ticket 25 links a sent mail.

## Shape

- Add Sent Items to one person's flow (same Teams folder); send three
  replies in one thread from Outlook desktop and one from the web.
- Record, headers' shape only (counts, never ids or addresses): Message-ID,
  In-Reply-To, References count, Thread-Index, and whether the trigger's
  `conversationId` can be written beside the file.
- Write the result into `infra/onprem/README.md` (the flow's steps) and
  ADR 0009.

## Acceptance

1. The measurement is written down with the date and the client versions.
2. Ticket 25 knows which link it uses: headers, or `conversationId`.
