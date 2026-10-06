# 02 — Ngữ cảnh hỗ trợ: MFA, route mặc định từ chối, audit

Status: ready-for-agent
Blocked by: 01
Area: platform-runtime

## Mục tiêu

Nhân viên hỗ trợ dùng danh tính của chính họ, có xác thực hai lớp, và chỉ mang scope đóng
dấu trong quyền. Route nào không khai mở cho hỗ trợ thì từ chối ngữ cảnh hỗ trợ: thiếu scope
chỉ chặn được route có kiểm scope, còn `GET /runs/{id}` hôm nay không kiểm scope nào, nên
mặc định từ chối là chỗ chặn thật (failure-modes #5).

## Việc cần làm

1. **Claim xác thực.** `VerifiedIdentity` (`application/ports.py:26`) thêm `auth_methods:
frozenset[str]` (từ `amr`) và `acr: str | None`. Adapter OIDC
   (`adapters/identity/keycloak.py`) đọc hai claim; adapter dev (`dev_token.py`) đọc từ token
   dev (chỉ profile không triển khai, như hôm nay).
2. **Keycloak.** Trong `infra/keycloak/dw-realm.json`: nhóm `dw-support`, OTP là required
   action cho thành viên nhóm, mapper đưa `amr` (hoặc `acr` theo mức) vào access token.
   Trước khi viết bộ kiểm, đăng nhập thật một user của nhóm qua compose và ghi vào Comments
   token trả claim nào, giá trị gì, có và không có OTP (failure-modes #4). Bộ kiểm dựa vào
   giá trị đo được.
3. **Bộ dựng** `SupportAccessContextFactory` (`dw_platform/application/support_access.py`):
   danh tính đã xác minh → có trong `support_staff` → có yếu tố thứ hai (thiếu → 403
   `support_mfa_required`) → `platform.support_grant_for_staff(id)` → `grant_effective_state`
   của ticket 01 là `active` → tenant có cờ `support_access`. Mã lỗi:
   `support_staff_required`, `support_mfa_required`, `support_grant_ended` (kèm `ended_at`,
   `ended_reason` `expired|revoked|ineffective`), `support_access_not_enabled`.
4. **AccessContext** thêm `support: SupportScope | None` (`grant_id`, `code`,
   `resource_type`, `resource_id`, `scope_set_key`). Ngữ cảnh hỗ trợ: tenant, workspace lấy
   từ quyền (không từ header của client); `roles` rỗng; `scopes` bằng bản đóng dấu;
   `principal_id` là nhân viên. Không qua `CachingMembershipLookup`. Không hợp với vai nào
   của nhân viên, kể cả `platform_admin`.
5. **Dependency** (`apps/api/src/dw_api/dependencies/auth.py`). `RequireAccessContext` gặp
   header `X-DW-Support-Grant` thì 403 `support_context_not_allowed`. Thêm
   `RequireAccessContextOrSupport`: có header thì dựng ngữ cảnh hỗ trợ, không thì như cũ. Sau
   khi dựng, ghi một audit `support.access` (`actor_id` nhân viên; `details`:
   `support_grant_id`, `method`, mẫu route, tham số đường dẫn là id; không query string,
   không body).
6. **Bảng route cho phép.** Hằng `SUPPORT_ALLOWED_ROUTES` ở composition root, rỗng trên
   `main`. Test duyệt `app.routes`: tập route có `RequireAccessContextOrSupport` phải bằng
   đúng hằng đó. Context thêm route vào hằng trong cùng thay đổi với test âm của nó.
7. **Kiểm lại trước khi ghi.** Một hàm công khai `recheck_support_grant(context)` dùng cùng
   bước 3 để thao tác dài (tải tệp lớn) gọi ngay trước bước ghi cuối.
8. **"Quyền của tôi".** Hàm `SECURITY DEFINER` `platform.support_grants_for_staff()` (không
   tham số; đọc `app.principal_id`) trả mã, tên công ty, tên workspace, nhãn phạm vi, nhãn chế
   độ, `resource_type`, `resource_id`, `scope_set_key`, `expires_at`, trạng thái suy ra, của
   quyền giao cho người gọi, kết thúc trong 30 ngày gần nhất. Route `GET /support/my-grants`
   (danh tính đã xác minh, phải ở `support_staff`, không cần tenant).
9. **Bootstrap.** `GET /auth/bootstrap` thêm `is_support_staff`.
10. **Route audit.** `GET /audit/events` thêm lọc `support_grant_id`, trường
    `actor_display_name` (join `platform.users`; không khớp → `null`), `actor_kind` (`user`,
    `support` khi `details.support_grant_id` có). Kiểm scope và lọc workspace của route là
    ticket 02 của `approval-audit-and-workspace`, không làm ở đây.
11. Wiring; `make generate-contracts`.

## Tiêu chí chấp nhận

Integration (`dw_platform/tests/integration` và `apps/api/tests`; một route test có
`RequireAccessContextOrSupport` đăng ký trong fixture):

- [ ] SA4: nhân viên có membership `platform_admin` ở một tenant khác dựng ngữ cảnh từ quyền
      ở tenant A → `context.roles == frozenset()`, `scopes` đúng bản đóng dấu; route test đòi
      scope ngoài bản đóng dấu → 403 (không qua nhánh `admin_role` của
      `authorization.py:47-49`). Không có khóa cache nào cho ngữ cảnh hỗ trợ sau request.
- [ ] SA5: token không có yếu tố thứ hai → 403 `support_mfa_required`. Gỡ kiểm → test đỏ.
- [ ] SA6: `expires_at` đã qua (đồng hồ giả) → 403 `support_grant_ended`, `expired`; thu hồi
      rồi gọi lại → `revoked`; gỡ vai người cấp → `ineffective`. `recheck_support_grant` sau
      thu hồi → lỗi cùng mã.
- [ ] SA7: với header hợp lệ, `GET /runs/{id}`, `GET /approvals`, `GET /knowledge/...`,
      `GET /audit/events`, `GET /admin/members` → 403 `support_context_not_allowed`. Test bảng
      route xanh với hằng rỗng; thêm `RequireAccessContextOrSupport` vào một route mà không
      thêm vào hằng → test đỏ.
- [ ] SA10: ba request dưới ngữ cảnh hỗ trợ → ba dòng `support.access` có
      `support_grant_id`; lọc theo `support_grant_id` thấy đúng ba dòng; nhân viên gọi
      `/audit/events` → 403.
- [ ] SA11: tenant tắt cờ sau khi cấp → ngữ cảnh không dựng được.
- [ ] SA12: `support_grants_for_staff()` với `app.principal_id` là người khác → 0 dòng;
      `support_grant_for_staff` cho quyền của người khác → 0 dòng. Test hỏi catalog: hai hàm
      là `SECURITY DEFINER`, `PUBLIC` không có quyền chạy.
- [ ] SA13: header hỗ trợ kèm `X-Tenant-Id`, `X-Workspace-Id` của tenant B hay ws2 → ngữ cảnh
      lấy tenant, workspace từ quyền; route test không trả dòng nào của tenant B hay ws2.
- [ ] Comments: claim Keycloak đo được, bản token đã che chữ ký.
- [ ] `reviewing-deployment-security` trên header mới, route mới, cấu hình realm.
- [ ] `make ci` xanh.

## Nguồn

- `apps/api/src/dw_api/dependencies/auth.py:67`; `dw_platform/application/access_context.py`;
  `adapters/persistence/caching_lookup.py:100`; `application/cache.py` (cache fail-open);
  `apps/api/src/dw_api/routes/v1/runs.py:41-58`, `approvals.py:44-76`, `audit.py:39-72`,
  `auth.py:32-38`.
- `spec.md` của lát này: Ngữ cảnh hỗ trợ (Mục tiêu 2), SA4–SA7, SA10–SA13, câu hỏi còn mở 1.

## Comments
