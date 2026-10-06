# 01 — Quyền hỗ trợ: bảng, vòng đời, route phía khách và đội hỗ trợ

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Khách nhờ, đội vận hành chọn người, quyền có hạn và thu hồi được. Ticket này dựng dữ liệu
và vòng đời của quyền hỗ trợ, phía khách (yêu cầu, cấp, duyệt, từ chối, thu hồi, xem) và
phía đội vận hành (danh sách nhân viên hỗ trợ, giao người). Dựng ngữ cảnh truy cập từ quyền
là ticket 02.

## Việc cần làm

1. **ADR.** Viết ADR trung tính "Customer-granted support access" ở `docs/adr/` (lý do nền
   tảng, không dẫn tài liệu sản phẩm), status Accepted khi Đạt duyệt, cùng thay đổi với
   code. Chọn số và tên tệp chưa dùng ở `main` lẫn ở nhánh nào đang merge từ `main`, để
   merge không đè một tệp đang có.
2. **Migration** theo mục Dữ liệu của `spec.md`:
    - `platform.support_staff`; `dw_app` SELECT; vai provisioner SELECT, INSERT, DELETE.
    - `platform.support_grants`: cột, CHECK theo trạng thái (mỗi nhóm cột có khi và chỉ
      khi đúng trạng thái), RLS tenant FORCE, index, FK có `ON DELETE` và index; grant như
      spec.
    - `UPDATE platform.roles SET scopes = scopes || '["support.request"]' WHERE key =
'org_admin'` (có downgrade).
    - Cờ `support_access`: không thêm vào gói nào.
    - Dòng trong `test_privileges.py`; `test_rls_coverage.py` thấy bảng mới.
3. **Application** `dw_platform/application/support_access.py`:
    - `SupportScopeCatalog`: `register(key, label, scopes, resource_types)`; từ chối bộ có
      scope bắt đầu bằng `approvals.`, `runs.`, `audit.`, `knowledge.`, `memory.`,
      `platform.`, `support.`, `directory.`; từ chối khóa trùng; đóng băng sau khi composition
      root dựng xong.
    - `SupportResourcePort` (Protocol, consumer là nền tảng): `describe(context,
resource_type, resource_id) -> str | None`; `None` thì tài nguyên không có trong
      workspace (404). `resource_type = 'workspace'` do nền tảng tự trả nhãn.
    - `SupportGrantService`: `Request`, `Approve`, `Reject`, `Revoke`, `List`. Có
      `support.grant`: kiểm `scopes(bộ) ⊆ scopes của người cấp trong workspace đó`, ghi
      `pending_assignment`, đóng dấu `scopes`, `granted_by`. Chỉ `support.request`: ghi
      `pending_approval`. Duyệt kiểm tập con theo người duyệt. Từ chối bắt lý do. Thu hồi mọi
      trạng thái chưa kết thúc.
    - Một hàm `grant_effective_state(grant, now, grantor_scopes)` trả `active`, `expired`,
      `ineffective` (người cấp không còn `support.grant` hoặc một scope đã đóng dấu) hay
      trạng thái lưu. `List` dùng nó; ticket 02 dùng đúng hàm này.
    - Audit cùng giao dịch: `support.grant.requested`, `.approved`, `.rejected`, `.revoked`;
      `details` gồm `support_grant_id`, `code`, `scope_set_key`, `resource_type`; không lý do.
4. **Route** `apps/api/src/dw_api/routes/v1/support.py` theo bảng API của `spec.md`.
   `RequireIdempotency` trên mọi POST. Body `extra="forbid"`. RLS của bảng chỉ lọc tenant,
   nên repository lọc thêm `workspace_id` của người gọi (lấy từ `AccessContext`) ở mọi đọc
   và mọi lệnh theo id; quyền của workspace khác là 404. `support.request` chỉ thấy yêu cầu
   do chính mình gửi. Tenant chưa có cờ `support_access`: `GET /support/catalog`, `GET` và `POST
/support/grants` trả 403 `support_access_not_enabled` (web đọc mã này để khóa nút kèm lý do).
5. **Phía đội vận hành** (ProvisioningContext, Platform Operator): `GET/POST/DELETE
/platform/support-staff`; `GET /platform/support-requests` (mọi tenant, chỉ
   `pending_assignment`: mã, tên công ty, workspace, nhãn phạm vi, nhãn chế độ, thời hạn
   xin, lý do, lúc gửi); `POST /platform/support-requests/{id}/assign` (ghi `staff_user_id`,
   `assigned_by`, `activated_at`, `expires_at`; audit provisioning và
   `support.grant.assigned` vào tenant). Không kiểm xung đột lợi ích (spec, câu hỏi còn mở
   2): docstring ghi rõ.
6. **Membership từ chối nhân viên hỗ trợ**: `GrantMembershipHandler` trả 409
   `support_staff_not_member` khi user ở `support_staff`. Đường đặt membership mới của
   `tenant-members-and-invitations` dùng cùng kiểm.
7. **Console** `/platform` (khung hiện có, operator only): bảng "Support requests" (giao
   người bằng `Select` chỉ gồm danh tính trong `support_staff`) và "Support staff" (thêm theo
   email, gỡ). Không cột nội dung hay số liệu nghiệp vụ.
8. Wiring ở `apps/api/src/dw_api/bootstrap/wiring.py`; `make generate-contracts`. Catalog
   rỗng trên `main`: `GET /support/catalog` trả `[]`, `POST /support/grants` trả 422
   `support_scope_set_unknown`.

## Tiêu chí chấp nhận

Unit:

- [ ] `SupportScopeCatalog` từ chối bộ có `approvals.decide`, `runs.read`, `platform.admin`;
      từ chối khóa trùng; đăng ký sau khi đóng băng → lỗi. Gỡ danh sách tiền tố cấm → test đỏ.
- [ ] `grant_effective_state`: `active` trước `expires_at`, `expired` đúng tại `expires_at`;
      `ineffective` khi người cấp mất `support.grant` hoặc mất một scope đã đóng dấu.

Integration (`dw_platform/tests/integration`, PostgreSQL compose; catalog có một bộ test
đăng ký trong fixture):

- [ ] SA1: vai không có `support.*` gọi `POST /support/grants` → 403; `org_admin` → dòng
      `pending_approval`; không đường nào đưa dòng đó sang `active` khi chưa duyệt.
- [ ] SA2: người cấp thiếu một scope của bộ → 403 `support_scope_not_held`, không dòng nào
      được ghi. Gỡ kiểm tập con → test đỏ.
- [ ] SA3: body có `staff_user_id` → 422; giao cho user không ở `support_staff` → 409; giao
      cho quyền đã `active` hoặc `rejected` → 409.
- [ ] SA9: `POST /admin/members` với email nhân viên hỗ trợ → 409 `support_staff_not_member`.
      Gỡ kiểm → test đỏ.
- [ ] SA11: tenant không có cờ → `GET /support/catalog` và `POST /support/grants` 403
      `support_access_not_enabled`; bật qua `feature_overrides` → 201.
- [ ] SA13: người tenant B, và người giữ `support.grant` ở ws2 của tenant A, đọc, duyệt, từ
      chối, thu hồi quyền của ws1 tenant A theo id → 404, dòng không đổi, không audit mới;
      `GET /support/grants` của họ không có quyền đó; kết nối không gắn tenant đọc 0 dòng.
- [ ] CHECK: chèn `status='active'` thiếu `expires_at` → check violation;
      `duration_hours=337` → check violation; `dw_app` DELETE → permission denied.
- [ ] Audit: mỗi lệnh đúng một sự kiện, có `support_grant_id`, không có `reason`.
- [ ] `make ci` xanh.

## Nguồn

- `packages/python/dw_platform/src/dw_platform/application/membership_admin.py` (chống leo
  thang, audit cùng giao dịch); `application/provisioning.py` (khuôn operator);
  `db/migrations/sql/0001_platform_baseline.sql:340` (`platform_operators`), `:213`
  (`feature_overrides`); `application/authorization.py:47-49`.
- `spec.md` của lát này: Dữ liệu, API, SA1–SA3, SA9, SA11, SA13.

## Comments
