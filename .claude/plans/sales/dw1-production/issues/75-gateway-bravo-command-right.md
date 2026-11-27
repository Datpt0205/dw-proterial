# 75 — Gateway: Bravo's command right, measured

Status: ready-for-human — code done 2026-11-26; script 10 on UAT fills `COMMAND_KEYS`
Blocked by: none
Category: research → enhancement (ticket 63 check 3)

## Why

The live `command_right` answers "unknown", so every live write is refused.
`02-trace-3.csv` shows no rights call at save: the client calls
`usp_sys_GetControlPermission(@UserId, '<screen>')` when a screen opens,
`ufn_sys_GetTablePermissionExprAll` per table, and gets the rest at login
(`usp_sys_Login`, compressed). Bravo's permission editor shows the storage:
`B00Permission` (`UserId` or `RoleId`, `NoOpen`, `NoDisplay`, `NoInherit`,
`IsActive`) joined to `B00PermissionData` (`ParentCommandKey`,
`SubCommandKey`: New, Edit, Print, Export, Delete…). How a user's row, its
roles' rows and `NoInherit` combine is not visible in SQL.

## What

1. Script `docs/proterial/sql/10` (read only, UAT): for 3 users whose Bravo
   behaviour is known (one may edit SO, one may only view, one denied by a
   user row over a role), list their `B00Permission` rows for `BizDocSO`, and
   the output of `usp_sys_GetControlPermission` for `EDIT_BizDocSO`. Đạt notes
   what each user can do in the client.
2. From that: the rule (user row over role rows unless `NoInherit`, or what
   the data shows) as one function in the SQL Server adapter, with the three
   users as tests. Anything the rule cannot place stays "unknown" (refused).

## Acceptance

- The three measured users each get the answer the client gives them.

## Comments

**2026-11-26, the rule is Bravo's own.** The schema (`03-B8_Hitachi_Cable_schema.sql`)
holds `ufn_B00Permission_Getdata(@_UserId, @_RoleId, @_PermissionType)`: it
folds a user's rows, their parent groups' and their roles' by `BuiltinOrder`,
`NoInherit` cutting what lies above (`usp_sys_GetControlPermission` does the
same per column); type 1 is by command (NoOpen/NoDisplay), 2 by sub-command,
3 the editing form's operations (NoAddNew, NoEdit…). So the gateway does not
re-derive anything: `SqlServerBravo.command_right` reads that function for the
three types and `decide_command_right` applies the deny-list (a flag on the
screen's commands denies; no row allows). Which keys carry the SO screen's
rights (`BizDocSO` with sub-commands Edit/Save/New? `EDIT_BizDocSO`?) is the
one unmeasured fact: `COMMAND_KEYS` is empty, so the answer stays "unknown"
and every live write is refused until script 10's three users show the keys
reproduce what the client lets each do. Unit 10 (deny/allow per type, a
flag on another command does not deny, the empty map); SQL Server 21/21 with
the function's shape stubbed; the deny line mutated → red. Script 08 (local)
grants the read login SELECT on the function. Script 10 (local,
`docs/proterial/sql/10-quyen-lenh-so-uat.sql`) is ready for the UAT session.
