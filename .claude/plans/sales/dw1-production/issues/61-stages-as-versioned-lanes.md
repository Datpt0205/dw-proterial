# 61 — DW1's stages as versioned lanes: pinned per case, rolled out per PIC

Status: needs-triage
Blocked by: none
Category: architecture (inside the modular monolith; no new services)

## Why

Another FPT team (ATLAS) runs many small workers so that a change ships beside
the running version instead of stopping it. Đạt, 11-20: learn the idea, do not
split into services; one host and six PICs do not need them.

Today DW1 is one context (`dw_sales`, about 110 application modules) in the API
and worker processes.

- Its stages exist as modules, and a case moves by its state machine.
- A deploy changes the code under every case at once.
- Only prompts, skills and artifacts are pinned per case (`release_manifest_ref`).

## Shape

- **Stages become worker lanes**, each with its own version and on/off switch:
  read documents, check (rules, mostly Bravo's), wait for people (PC, Design,
  customer, PIC; read from Bravo and mail), write Bravo (the shared Bravo gate,
  DW1 and DW2), communicate.
- **Pinning.** A case records the version of each stage it started with and
  finishes on it. New cases take the new version. The release manifest grows
  from prompts and skills to stage rule sets.
- **Rollout.** A new stage version goes to one PIC first. It also runs in shadow
  beside the old one and is compared before it is promoted.
- **Per person.** Each PIC sees "my DW": their queue, memory and per-case chats.
  Underneath it is the same logic, with cases routed by the customer's Sales
  PIC (`B20Customer.EmployeeCode_Salesman`).

## Acceptance

1. A case started on stage version N finishes on N after N+1 is deployed (test).
2. A version can be switched on for one PIC only.

## Comments
