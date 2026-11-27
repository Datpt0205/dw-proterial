# 01 — Watchdog: a person's mail folder with no new mail is told to an admin

Status: ready-for-agent
Blocked by: none
Category: platform / mail

## What

`docs/dev/viec-chung-dw1-dw2.md` §5, ⚑ UAT: "**Watchdog**: thư mục của một
người không có thư mới quá N giờ làm việc → báo admin (flow chết im lặng)".

Checked 2026-11-27: not built. `DwLaneStale` (`infra/prometheus/alerts.yml:113`,
`821ce89e`) fires when a lane stops ticking, and the host watchdog
(`infra/onprem/windows-host/host-watchdog.ps1:153`, section 4b) says when
dwmail's OneDrive stops; neither sees one person's Power Automate flow die
while the lane and OneDrive keep running. Power Automate turns a flow off
after 14 days of failures or 90 idle days (the doc's §5 note), so that is the
failure to catch.

## Design

- **Owner: the platform.** The drop folder is a platform port
  (`dw_platform.application.drop_folder.DropFolderPort`, `FolderOwnersPort`);
  which DW reads a folder is each context's lane, but whether mail still
  arrives in it is one question for every DW. New
  `dw_platform.application.mail_folder_watch` (`MailFolderWatch`): for each
  (tenant, workspace) a mail drop runs in, the folders of members who own one
  (`FolderOwnersPort`), the newest `DroppedFile.modified_at` per folder
  (`DropFolderPort.files()` already lists one level below the root).
- **"N working hours" is tenant config**, not a constant: a platform policy
  `configs/policies/mail_watch@1.0.0.yaml` (`quiet_after_working_hours`,
  working days and hours) resolved per tenant through the rule versions /
  `TenantOverlay` like `retention`; the platform file ships a default and says
  so. Working time is counted in the tenant's zone.
- **State, so it tells once:** `platform.mail_folder_watch` (migration from
  `alembic revision`): tenant, workspace, folder, `last_file_at`,
  `quiet_since`, `told_at`; RLS enabled and FORCEd with the workspace policy
  shape; grants in the migration and in `test_privileges.py`.
- **Told:** a notice through the platform's `deliver` to holders of the
  member-admin scope (`platform.members.write`) in that workspace, source key
  `platform.mail_folder.quiet:<folder>:<last_file_at>` (one per quiet spell;
  pushed by the existing `web_push_delivery` lane), and again "có thư lại"
  when a file arrives. The folder name (a mailbox address) is in the notice;
  no subject or sender of any mail.
- **For the ops side:** a gauge `dw_mail_folders_quiet` per tenant (safe ids
  only) and an alert `DwMailFolderQuiet` in `infra/prometheus/alerts.yml`,
  with its case in `alerts.test.yml`, so it reaches the host watchdog's mail
  (`4901f0b3`).
- **Worker:** lane `mail_folder_watch` registered at
  `apps/worker/src/dw_worker/main.py` (every 15 min), audited as itself
  (`lane_audit_event`, `system:mail_folder_watch`), reporting its clean tick
  like every lane.

## Acceptance

- Unit: a folder quiet past N working hours is told once; a weekend or a
  night does not count; a new file clears it and says so; a folder owned by
  nobody holding a reading scope is not watched; the threshold read from a
  tenant version, the platform default otherwise.
- PostgreSQL: RLS on the new table (tenant A's lane state invisible to B, a
  connection with no tenant reads nothing); privileges asserted.
- Negative: tenant B's admin is never told of tenant A's folder.
- Mutation: drop the working-hours count, the once-per-spell key, the tenant
  filter: each turns a test red.

## Owed

- Đạt: the default N for Proterial (the tenant can change it later).
