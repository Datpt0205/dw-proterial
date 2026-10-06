# 01 — Người dùng toàn tenant, sửa vai theo workspace, lời mời

Status: ready-for-agent
Blocked by: .claude/plans/platform-runtime/support-access/issues/01-support-grants-lifecycle.md
Area: platform-runtime

## Mục tiêu

Quản trị viên tổ chức thấy mọi người của tenant với vai ở từng workspace, sửa vai của một
người ở nhiều workspace trong một lần lưu, và mời một người chưa từng đăng nhập bằng email
(spec, Hiện trạng).

## Việc cần làm

1. **Danh sách toàn tenant.** `GET /api/v1/admin/members` (`platform.members.read`): mỗi
   người `user_id`, `display_name`, `email`, `status` (`invited` khi user chưa có dòng
   `platform.external_identities`, không thì `active`), `memberships`: [{`workspace_id`,
   `workspace_name`, `role_keys`}]. Đọc dưới RLS tenant của người gọi. Sắp theo tên với
   collation tiếng Việt nếu image PostgreSQL có (`SELECT collname FROM pg_collation WHERE
collname LIKE 'vi%'`; đo, ghi vào Comments), không thì theo `display_name` mặc định; có
   index phục vụ thứ tự đó, đứng đầu là `tenant_id`.
2. **Sửa vai nhiều workspace.** `PUT /api/v1/admin/members/{user_id}/memberships`
   (`platform.members.write`, `Idempotency-Key`). Body `memberships`: [{`workspace_id`,
   `role_keys`}]. Một giao dịch:
    - chỉ thay vai không quản trị (vai không mang scope `platform.*`); vai quản trị người đó
      đang giữ ở mỗi workspace giữ nguyên;
    - `role_keys` có vai quản trị mà người gọi không phải Platform Admin → 403
      (`_forbid_escalation`);
    - workspace có trong body mà chưa có membership → tạo; có membership mà không có trong
      body → bỏ vai không quản trị, còn vai quản trị thì giữ membership, không còn vai nào thì
      gỡ;
    - workspace ngoài tenant → 404; vai lạ → 404 kèm danh sách;
    - mỗi thay đổi một audit `platform.membership.grant` hoặc `.revoke`;
    - xóa cache AccessContext của từng workspace bị đổi (`membership_cache_pattern`).
3. **Lời mời.** `POST /api/v1/admin/invitations` (`platform.members.write`,
   `Idempotency-Key`): `display_name` (4–120), `email`, `memberships` (như bước 2, ít nhất một
   dòng có vai). Một giao dịch: email chuẩn hóa chữ thường; đã là thành viên tenant → 409
   `member_email_exists_in_tenant`; user ở `platform.support_staff` → 409
   `support_staff_not_member`; user chưa có → tạo `platform.users` (tên hiển thị, email),
   không tạo `external_identities`; rồi đặt membership như bước 2; audit
   `platform.member.invited` (`details`: `user_id`, workspace, vai; không email). Lần đăng
   nhập đầu, `identity_provisioning.py` nối danh tính vào user này theo email đã xác minh.
   Viết test chứng minh đường nối đó chạy với user tạo từ lời mời (failure-modes #4).
4. **Directory.** `GET /directory/members` thêm `status`, cùng hàm tính với bước 1 (một chủ).
5. **Chặn nhân viên hỗ trợ ở mọi đường đặt membership**: `PUT …/memberships` cũng trả 409
   `support_staff_not_member` (cùng kiểm với `GrantMembershipHandler`, `support-access`
   ticket 01).
6. Không gửi email. Docstring ghi: người quản trị báo người được mời ngoài sản phẩm; gửi email
   là P1.
7. `make generate-contracts`.

## Tiêu chí chấp nhận

Integration (`dw_platform/tests/integration`, `apps/api/tests`):

- [ ] TM2: `GET /admin/members` của `org_admin` tenant A không chứa người chỉ thuộc tenant B;
      người không có `platform.members.read` → 403. `PUT …/memberships` với `user_id` hay
      `workspace_id` của tenant B → 404, không membership nào được tạo hay đổi.
- [ ] TM1: người giữ `org_admin` và một vai thường ở ws1; `PUT` chỉ đổi vai thường →
      `org_admin` còn. `PUT` có `org_admin` do `org_admin` gọi → 403 và không membership nào
      đổi (cả giao dịch lùi). Gỡ phần giữ vai quản trị → test đầu đỏ.
- [ ] `PUT` bỏ ws2 khỏi body → membership ws2 bị gỡ, có audit `.revoke`; cache của ws2 bị xóa
      (cache giả trung thực).
- [ ] Lời mời: email mới → user tạo, `status=invited`, membership đúng; đăng nhập lần đầu bằng
      token dev có cùng email → bootstrap thấy workspace đó, `status=active`. Email đã là
      thành viên → 409.
- [ ] TM3: email nhân viên hỗ trợ → 409 ở `POST /admin/invitations` và `PUT …/memberships`.
      Gỡ kiểm → test tương ứng đỏ.
- [ ] TM4: hai lời mời đồng thời cùng email → một 201, một 409.
- [ ] `Idempotency-Key` gửi lại cùng body → cùng kết quả, không audit thứ hai.
- [ ] `make ci` xanh.

## Nguồn

- `apps/api/src/dw_api/routes/v1/admin_members.py:44`, `directory.py:38`;
  `packages/python/dw_platform/src/dw_platform/application/membership_admin.py:41-42, 123-159`;
  `adapters/persistence/identity_provisioning.py` (nối theo email);
  `application/cache.py:23`; `db/migrations/sql/0001_platform_baseline.sql:616`.
- `spec.md` của lát này: Kiểm soát TM1–TM4, câu hỏi còn mở 1.

## Comments
