# 75 — Gateway: Bravo's command right, measured

Status: ready-for-human (a script on UAT), then ready-for-agent
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
