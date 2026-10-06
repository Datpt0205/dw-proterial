# Offboarding thấy mọi workspace của tenant

Status: resolved
Area: platform-runtime · Nhánh: `main` · Viết: 3/10/2026

Lát nền tảng, trung tính với sản phẩm. Một context có thể cho RLS của bảng mình lọc
cả tenant lẫn workspace: `tenant_id` khớp `app.tenant_id` và `workspace_id` khớp
`app.workspace_id`. Lane offboarding hôm nay chỉ gắn `app.tenant_id`
(`packages/python/dw_platform/src/dw_platform/adapters/persistence/offboarding.py:39,
150, 170`), nên với một bảng như thế:

- lượt xuất đọc 0 dòng; bundle thiếu dữ liệu của tenant mà không báo gì;
- lượt xóa không xóa được dòng nào, vì `DELETE` cũng qua policy;
- rồi lượt xóa tới `platform.workspaces` của tenant (`dw_app` có DELETE ở đó). Khóa
  ngoại `ON DELETE CASCADE` xóa các dòng chưa xuất, vì tác vụ khóa ngoại không qua
  RLS, nên dữ liệu mất hẳn. Khóa ngoại `RESTRICT` thì lượt xóa hỏng.

Lát này cho lane offboarding một setting mở rộng có chủ đích,
`app.workspace_scope = 'tenant'`, và cho `test_rls_coverage.py` hai luật đi kèm:
setting đó chỉ được đọc cùng vế tenant, và một bảng lọc theo workspace phải đọc nó.

Hôm nay `main` chưa có bảng nào lọc theo workspace (không policy nào đọc
`app.workspace_id`), nên lát này không đổi hành vi của bảng nào đang có. Nó phải có
trước migration đầu của context đầu tiên lọc theo workspace.

## Mục tiêu

- Bảng có RLS lọc tenant và workspace được lane offboarding xuất đủ và xóa đủ, ở mọi
  workspace của tenant.
- Setting mở rộng không bao giờ mở sang tenant khác: test đỏ khi một policy đọc nó mà
  vế `app.tenant_id` không đứng trong cùng một AND ở mức ngoài cùng của biểu thức.
- Bảng lọc theo workspace mà quên vế `app.workspace_scope` thì test đỏ ngay ở
  migration đầu của nó, không đợi tới lượt offboarding thật.
- Chỉ lane offboarding gắn setting này, theo từng giao dịch; kết nối không còn mang
  nó sau giao dịch.

## Dạng policy

Bảng lọc theo workspace dùng đúng dạng này cho cả `USING` lẫn `WITH CHECK`:

```sql
tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
AND (
    workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid
    OR current_setting('app.workspace_scope', true) = 'tenant'
)
```

- Vế tenant luôn áp. Setting mở rộng chỉ bỏ vế workspace, không bao giờ bỏ vế tenant.
- Dạng `NULLIF(…, '')` như mọi policy đang có: setting đã gắn rồi hết giao dịch trở
  thành chuỗi rỗng, ép thẳng sang uuid sẽ lỗi.
- Tên policy `tenant_isolation_<bảng>`: lane offboarding tìm bảng theo tiền tố này
  (`offboarding.py:53-71`).
- `app.workspace_id` do `tenant_session` gắn từ AccessContext đã xác minh, theo giao
  dịch (`tenant_session.py:23-27`); không đổi.

## Trong phạm vi

- `offboarding.py`: `export_rows` và `purge_rows` gắn `app.workspace_scope = 'tenant'`
  cùng `app.tenant_id`, bằng `set_config(..., true)`, trong cùng giao dịch.
  `claim_requested` và `mark_status` không đổi: chúng chỉ chạm
  `platform.tenant_offboarding_requests`.
- `test_rls_coverage.py`: hai luật mới (ticket 01).
- Test tích hợp với một bảng thử lọc theo workspace, và chứng minh đỏ cho từng chốt.
- `CLAUDE.md` mục "Tenancy and authorization": một dòng ghi dạng policy trên và ai
  gắn setting.

## Ngoài phạm vi

- Bảng nền tảng đang có (approvals, audit, runs…) vẫn chỉ lọc theo tenant. Lọc chúng
  theo workspace là việc khác.
- Job nền đọc chéo tenant bằng `app.worker_drain` (retention sweep,
  `claim_requested`) giữ nguyên: policy `worker_drain` cố ý không có vế tenant, và
  hai luật mới không áp cho nó.
- Đường đọc cấp tenant cho người dùng (ví dụ số tổng hợp mọi workspace): Câu hỏi còn
  mở 1.
- Object storage: lane offboarding xử lý theo tiền tố `{tenant_id}/`, không qua RLS
  (`apps/worker/src/dw_worker/consumers/offboarding.py`).

## Quy tắc và kiểm soát

Mỗi chốt có một test đỏ khi gỡ chốt (`failure-modes.md` #3):

| Chốt                                             | Test đỏ khi gỡ                                                                                                                           |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Lượt xuất thấy mọi workspace của tenant          | Bỏ dòng gắn `app.workspace_scope` ở `export_rows` → bundle thiếu dòng của bảng thử                                                       |
| Lượt xóa xóa ở mọi workspace của tenant          | Bỏ dòng đó ở `purge_rows` → bảng thử còn dòng của tenant                                                                                 |
| Setting không vượt tenant                        | Bỏ vế tenant khỏi policy của bảng thử → giao dịch gắn tenant B cùng `app.workspace_scope = 'tenant'` đọc được dòng của tenant A, test đỏ |
| Setting chỉ sống trong giao dịch                 | Đổi `true` thành `false` trong `set_config` → kết nối dùng lại còn mang setting                                                          |
| Setting mở rộng luôn đi cùng vế tenant           | Policy thử `tenant OR scope`, hay `(tenant AND workspace) OR scope` → `test_rls_coverage.py` đỏ, nêu tên policy                          |
| Bảng lọc theo workspace phải đọc setting mở rộng | Bảng thử chỉ có policy `tenant AND workspace` → `test_rls_coverage.py` đỏ, nêu tên bảng                                                  |

## Tiêu chí xong của slice

- Ticket 01 ở `Status: resolved`, ghi commit và các chứng minh đỏ dưới `## Comments`.
- `uv run pytest packages/python/dw_platform/tests/integration -m integration` xanh;
  `make ci` xanh.
- `.claude/plans/platform-runtime.md` có dòng cho lát.

## Phụ thuộc

- Dựng trên guard dò bảng từ catalog (commit `9ec3a89`): `test_rls_coverage.py` đã
  thấy mọi schema có bảng mang `tenant_id`, nên hai luật mới áp cho schema của mọi
  context, không cần ai liệt kê.
- Không chờ lát nào khác. Context đầu tiên lọc theo workspace chờ lát này: migration
  đầu của nó cần cả lane offboarding lẫn hai luật đã có.

## Câu hỏi còn mở

1. **Đường đọc cấp tenant sau này** (người có phạm vi tenant đã xác minh xem số tổng
   hợp mọi workspace) dùng lại `app.workspace_scope` hay một setting riêng? Đề xuất:
   dùng lại, để "đọc mọi workspace của một tenant" chỉ có một cách. Khi đó luật "chỉ
   lane offboarding gắn setting" đổi thành "chỉ backend gắn, từ phạm vi đã xác minh",
   và phép kiểm ở ticket 01 đổi theo. Nếu là setting riêng, nó theo cùng luật vế
   tenant.

## Danh sách ticket

| #   | Ticket                                                                                                                           | Status   | Blocked by |
| --- | -------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------- |
| 01  | [Lane offboarding gắn `app.workspace_scope`; guard RLS nhận nó chỉ cùng vế tenant](issues/01-workspace-scope-for-offboarding.md) | resolved | —          |
