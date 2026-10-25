# Tài khoản đăng nhập do IT của tenant tự tạo

Status: resolved (2026-10-25, Đạt; chưa push)
Area: platform-runtime · Viết: 25/10/2026

Đạt, 2026-10-25: "làm thêm cái cho IT bên họ tự add thêm user và gắn quyền cho user đó luôn
đi để khỏi phải tốn công gắn IdP hay AD nào khác". Đã chốt: mật khẩu tạm hiện một lần (không
cần máy chủ mail); IT gán được mọi vai nghiệp vụ (kể cả quyền xem giá), không vai quản trị.

## Đã dựng

- **Màn Thành viên** (`apps/web/components/admin/sign-in-accounts.tsx`): "Thêm người" (họ tên,
  email, vai) tạo người + vai + tài khoản Keycloak cùng lúc; hộp thoại mật khẩu tạm hiện một
  lần, bấm ra ngoài không đóng; mỗi dòng có "Đặt lại mật khẩu", "Khóa/Mở khóa đăng nhập", tắt
  kèm lý do bằng chữ khi không làm được. Danh sách vai đọc từ catalog (`administrative` do
  server tính bằng `is_administrative`), nên vai Sales hiện ra, vai quản trị chỉ cho Platform
  Admin.
- **Server** (`application/member_accounts.py`, `adapters/identity/keycloak_accounts.py`,
  `routes/v1/admin_accounts.py`): tạo tài khoản trước rồi `TenantMembersService.invite` (giữ
  nguyên luật cũ); lời mời bị từ chối thì xóa tài khoản vừa tạo. Reset/khóa chỉ với người của
  tenant (`manageable_member`), tài khoản quản trị chỉ Platform Admin, không tự khóa mình, và
  chỉ trên tài khoản mang `dw_tenant_id` của tenant đó. Audit `platform.login_account.*` ghi
  trong transaction commit sau khi Keycloak trả lời. Mật khẩu tạm không log, không audit, không
  vào bảng idempotency (replay trả `temporary_password: null`), gửi kèm `Cache-Control: no-store`.
- **Keycloak** (`infra/keycloak/dw-realm.json`): client `dw-accounts` (service account,
  `manage-users`/`view-users`/`query-users`); user profile `unmanagedAttributePolicy:
  ADMIN_EDIT`, email chỉ admin sửa. Secret từ `DW_API_ACCOUNTS_CLIENT_SECRET`, compose không
  khởi động Keycloak lẫn API khi thiếu; profile deployed từ chối giá trị `change-me…` hoặc
  dưới 32 ký tự. Realm đã có từ trước: `scripts/keycloak_accounts_client.py`.
- **Vá kèm:** `KeycloakTokenVerifier` coi email chưa xác minh (`email_verified` khác `true`)
  là không có, vì lần đăng nhập đầu nối người theo email.

## Người dùng tự đổi mật khẩu (2026-10-26, Đạt: "có làm đi")

- **Lần đầu:** Keycloak buộc đặt mật khẩu riêng trước khi vào DW (mật khẩu tạm mang
  `UPDATE_PASSWORD`).
- **Về sau:** "Đổi mật khẩu" trong menu tài khoản (`session-chip.tsx`) gọi
  `keycloak.login({ action: "UPDATE_PASSWORD" })`, đổi xong quay về đúng trang. Không có ở dev
  mode (không có Keycloak).
- **Tiếng Việt:** realm bật `internationalizationEnabled`, `defaultLocale: vi`; Keycloak 26.7.2
  có sẵn `messages_vi` cho login và account (đã mở jar theme để kiểm), không cần dịch thêm.
  `scripts/keycloak_accounts_client.py` áp cả ngôn ngữ cho realm có sẵn.
- **Quên mật khẩu:** vẫn nhờ IT "Đặt lại mật khẩu" (realm tắt quên mật khẩu, không có SMTP).
- **E2E qua trang Keycloak thật:** `make test-web-accounts`
  (`apps/web/e2e/sign-in-accounts.oidc.spec.ts`, `playwright.oidc.config.ts`): IT tạo người →
  đăng nhập bằng mật khẩu tạm → buộc đổi (tiếng Việt) → vào DW → "Đổi mật khẩu" → chỉ mật khẩu
  mới nhất đăng nhập được → IT gỡ người. Xanh 2026-10-26 (1,1 phút); bỏ `action` thì đỏ ở
  bước đổi mật khẩu. Chưa chạy trong CI: bộ e2e của CI chạy dev auth, không có Keycloak.

## Đo trên Keycloak 26.7.2 (2026-10-25)

- Thuộc tính không khai báo (`dw_tenant_id`) bị bỏ im lặng nếu realm không có `ADMIN_EDIT`.
- Service account có `manage-users` reset được mật khẩu cả realm admin: kiểm `dw_tenant_id`
  là lớp chặn duy nhất giữa tenant này với tài khoản của người khác.
- Người dùng đổi được email trong account console khi email còn cho user sửa; email thành
  `email_verified=false`, đăng nhập bị chặn vì `verifyEmail` + không có SMTP.
- `${DW_ACCOUNTS_CLIENT_SECRET}` không có biến môi trường lúc import thành secret đúng bằng
  chuỗi đó (ai đọc repo cũng biết).
- PUT một phần `{"enabled": false}` giữ các trường khác; mật khẩu tạm đặt `UPDATE_PASSWORD`.

## Kiểm

Unit `test_member_accounts.py` (13), `test_admin_accounts_endpoint.py` (5),
`test_keycloak_verifier.py`, `test_dev_endpoints.py` (secret); integration
`test_keycloak_accounts.py` (9, realm dựng từ chính `dw-realm.json`, CI chạy với
`DW_TEST_KEYCLOAK`); vitest `sign-in-accounts.test.tsx` (6). Mutation: 9 lá chắn server và 3
lá chắn realm đều đỏ khi gỡ.

## Còn mở

- Người thuộc hai tenant: tenant tạo tài khoản là tenant quản nó; khóa ở đó thì người này
  cũng không vào được tenant kia.
- Nối AD sau này (LDAP federation): bật "Trust Email" ở federation, nếu không email của người
  dùng AD là chưa xác minh và không nối được vào người đã được mời (đóng, không mở).
