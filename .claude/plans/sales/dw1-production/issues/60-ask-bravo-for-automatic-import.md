# 60 — Ask the Bravo vendor for an automatic Import path

Status: ready-for-human (Đạt asks the vendor, with Proterial IT)
Blocked by: none
Category: research

## Why

Đạt, 11-20: DW must perform the Import itself, not stop at a proposal. Creating
a document through Bravo's own engine keeps Bravo's logic owned by Bravo.

## Shape

Three questions to the vendor:

1. Can Bravo run an Import, or another scheduled task, without a person pressing
   the button? The database holds the CLR assemblies `BravoScheduleAuto` and
   `Microsoft.Win32.TaskScheduler`.
2. Would they write one procedure that creates an SO from a staging table under
   their own rules, as they did for Base price (`usp_B20BasePrice_GetData`
   behind GetData)? PR and PO would follow.
3. Do they accept DW's own rule runner (ticket 59) writing through a staged job,
   and will they review it?

Fallback while waiting: drive the client's Import button by UI automation on a
Windows host. This uses 100% of Bravo's engine. The document is then authored
by the robot account (`SALEAI`), with the PIC in the employee field. That
authorship needs Đạt's decision, since the standing decision is "under the PIC".

## Acceptance

The vendor's answer is recorded here, and ticket 51 picks its path.

## Comments
