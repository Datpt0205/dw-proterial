# 03 — Web: phiên quyền hỗ trợ, trang "Quyền hỗ trợ của tôi", chỗ cắm băng

Status: ready-for-human (built 13/10/2026 by the agent, Đạt away; owed: the Playwright run of `e2e/support-session.spec.ts`, which needs Docker, down since 22:00 that day — see Comments)
Blocked by: 01, 02, .claude/plans/web-ui/antd-shell/issues/03-lib-dates.md, .claude/plans/web-ui/antd-shell/issues/05-ui-test-harness.md, .claude/plans/web-ui/antd-shell/issues/06-app-feedback.md, .claude/plans/web-ui/antd-shell/issues/09-region-state-and-offline.md
Area: platform-runtime

## Mục tiêu

Nhân viên hỗ trợ thấy các quyền được giao, mở một quyền, và từ đó mọi request mang mã quyền
cho tới khi thoát hay quyền kết thúc. Shell và API client là code chung, nên phần này nằm ở
nền tảng; chữ của băng, menu và trang chặn trong ngữ cảnh hỗ trợ thuộc context.

## Việc cần làm

1. `apps/web/lib/support/session.ts`: quyền đang dùng (id, mã, tenant, workspace, loại tài
   nguyên, id tài nguyên, khóa bộ scope, hạn) trong `sessionStorage` (mọi đọc, ghi bọc
   `try/catch`), xóa khi "Thoát quyền hỗ trợ" hoặc khi API trả `support_grant_ended`.
2. API client (`apps/web/lib/session.ts`): có quyền đang dùng thì gửi `X-DW-Support-Grant`,
   và `X-Tenant-Id`, `X-Workspace-Id` lấy từ quyền, không từ workspace đang chọn.
3. `NavItem` thêm `supportStaffOnly`; bộ lọc menu đọc `is_support_staff` của bootstrap.
   Người là nhân viên hỗ trợ và không có membership nào thì trang đầu là `/support`.
4. Shell có chỗ cắm băng dưới header (cùng chỗ băng mất mạng của antd-shell ticket 09); một
   context cắm băng của nó vào đó khi `useSupportGrant()` có quyền đang dùng.
5. Registry trang đích theo khuôn `apps/web/lib/approvals/registry.ts`: context đăng ký
   `supportLanding(resource_type, scope_set_key, resource_id) -> href`; không có mục khớp thì
   về `/`.
6. Trang `apps/web/app/support/page.tsx` "Quyền hỗ trợ của tôi": h1, phụ đề "Dữ liệu của khách
   chỉ mở được qua quyền hỗ trợ do khách cấp. Mỗi quyền có phạm vi, chế độ và hạn; mọi thao
   tác ghi nhật ký với mã quyền."; bảng từ 992px: Khách · Workspace · Phạm vi · chế độ · Hết
   hạn (giờ Việt Nam qua `lib/dates.ts`) kèm "còn {h} giờ" (vàng dưới 4 giờ; "Đã hết hạn" hoặc
   "Khách đã thu hồi" đỏ) · Trạng thái · nút "Mở" (khóa khi đã kết thúc, lý do "Quyền đã hết
   hạn hoặc bị thu hồi."); dưới 992px bốn cột gọn; trống "Chưa có quyền hỗ trợ nào" · "Khi
   khách cấp quyền, quyền hiện ở đây kèm phạm vi và hạn."; trạng thái vùng bằng
   `RegionState`. Dữ liệu `GET /support/my-grants`. `support_mfa_required` → trang chặn "Cần
   xác thực hai lớp để dùng quyền hỗ trợ". "Mở" ghi quyền vào phiên rồi tới trang đích của
   registry.
7. Một hook `useSupportGrant()` (quyền đang dùng hoặc `null`) để context ẩn thao tác trong
   ngữ cảnh hỗ trợ.

## Tiêu chí chấp nhận

- [x] Vitest: client gửi `X-DW-Support-Grant` và tenant, workspace của quyền khi có quyền
      đang dùng, không gửi khi không có; nhận `support_grant_ended` thì phiên bị xóa;
      `sessionStorage` ném lỗi thì trang vẫn chạy, không có quyền đang dùng.
- [x] Vitest: registry trang đích trả `href` của mục khớp, `/` khi không khớp.
- [ ] Playwright (stack local, một context test đăng ký trang đích trong fixture): nhân viên
      có token dev hai lớp thấy quyền ở `/support`, bấm "Mở" tới trang đích, request kế tiếp
      có header; token không có yếu tố thứ hai → trang chặn; 320px, 992px, 1440px, sáng và
      tối; project `tz-los-angeles` của antd-shell ticket 05 vẫn ghi giờ Việt Nam.
- [x] Mục menu có `supportStaffOnly` chỉ hiện với nhân viên hỗ trợ; gỡ nhánh lọc → test đỏ.
- [x] `pnpm lint`, `pnpm typecheck`, `pnpm build` xanh; `reviewing-deployment-security` trên
      header mới ở client và trang `/support` (build: bước "Build web" của CI run
      38527044307, `6fc050a`, 14/10/2026).

## Nguồn

- `apps/web/lib/session.ts:146-147` (header tenant, workspace hôm nay);
  `apps/web/lib/nav/types.ts` (`operatorOnly` là tiền lệ); `apps/web/lib/approvals/registry.ts`.
- Ticket 01 (`support_access`), 02 (`GET /support/my-grants`, `is_support_staff`, mã lỗi).
- `spec.md` của lát này: Mục tiêu 3.

## Comments

- 8/10/2026: chưa làm. Đã có điều ticket này chờ: antd ở mọi trang, `RegionState`
  (`@dw/ui`), thông báo qua `App.useApp()`, `lib/dates.ts` theo giờ Việt Nam,
  `GET /support/my-grants` và `is_support_staff` (ticket 02). Còn nguyên bước
  1–7: phiên quyền trong `sessionStorage`, header `X-DW-Support-Grant` trong
  `clientOptions`, `supportStaffOnly`, chỗ cắm băng, registry trang đích, trang
  `/support`, `useSupportGrant()`. Lưu ý từ ticket 02: lần đăng nhập đầu sau khi
  cài OTP, token chỉ có `["pwd"]`, nên trang `/support` phải hiện trang chặn
  `support_mfa_required` kèm lời "đăng nhập lại".
- 13/10/2026, **làm bước 1–7** (agent, Đạt vắng, theo ủy quyền).
    - `apps/web/lib/support/session.ts`: quyền đang mở (id, mã, tenant,
      workspace, loại và id tài nguyên, khóa bộ scope, **scope đóng dấu**, hạn)
      trong `sessionStorage`, mọi đọc, ghi bọc `try/catch`; giá trị hỏng hay
      sai dạng đọc thành "không có quyền nào"; `useSupportGrant()`
      (`useSyncExternalStore`, nghe sự kiện của chính nó và `storage`).
    - `lib/session.ts`: có quyền đang mở thì gửi `X-DW-Support-Grant` và
      `X-Tenant-Id`, `X-Workspace-Id` của quyền, không của workspace đang chọn;
      403 có `details.reason_code` `support_grant_ended` thì đóng quyền,
      `support_mfa_required` thì đóng quyền và ghi cờ để `/support` hiện trang
      chặn.
    - `NavItem.supportStaffOnly`, `NavViewer.isSupportStaff`, mục "Quyền hỗ
      trợ" (`/support`); bootstrap đọc `is_support_staff`; nhân viên hỗ trợ
      không có membership vào được (như người vận hành) và về `/support` khi
      không có quyền đang mở.
    - Chỗ cắm băng: `AppShell` (`@dw/ui`) có prop `banner`, dưới thanh trên;
      `SupportBannerSlot` vẽ băng của context nếu context khai
      (`SupportHost.Banner`), không thì băng nền tảng (`role="status"`, mã
      quyền, hạn theo giờ Việt Nam, "Thoát quyền hỗ trợ").
    - Registry trang đích `lib/support/registry.ts` theo khuôn
      `lib/approvals/registry.ts`: Sales khai `sales.case_support` → `/sales/orders`
      (`app/sales/_meta/support.ts`); không khớp, hay trang ngoài app → `/`.
    - Trang `/support`: h1, phụ đề, bảng (Khách và mã · Workspace · Phạm vi ·
      chế độ · Hết hạn kèm "còn …" vàng dưới 4 giờ, "Đã hết hạn" hay "Khách đã
      thu hồi" đỏ · Trạng thái · "Mở" khóa kèm lý do khi đã kết thúc); dưới
      992px bỏ hai cột Workspace và Phạm vi; trống "Chưa có quyền hỗ trợ nào";
      lỗi qua `LoadError`/`RegionState`; trang chặn "Cần xác thực hai lớp để
      dùng quyền hỗ trợ" với nút đăng xuất để đăng nhập lại.
- **Decided by the agent (Đạt away), 13/10/2026:** `GET /support/my-grants`
  trả thêm `scopes` (bản đóng dấu trên quyền), và khi một quyền đang mở,
  `useAuth()` cho `roles` rỗng và `scopes` bằng bản đó. Không có nó, trang
  của context (Sales chặn bằng `ScopeGate`) thấy nhân viên không có scope
  nào và vẽ 403 mà không gửi request nào, nên không request nào mang mã
  quyền và cũng không bao giờ biết `support_mfa_required`. Máy chủ vẫn quyết
  mọi request (SA4: ngữ cảnh hỗ trợ là vai rỗng, scope đóng dấu); màn hình
  chỉ hiện đúng điều máy chủ sẽ cho.
- **Test, mutation.** Vitest `lib/support/__tests__/support-session.test.ts`
  (header và tenant, workspace của quyền; không header khi không có quyền;
  `support_grant_ended` đóng quyền, lý do khác giữ; `support_mfa_required`
  đóng và ghi cờ; `sessionStorage` ném lỗi thì request vẫn chạy, không quyền
  nào; giá trị hỏng bị bỏ), `registry.test.ts` (khớp, không khớp → `/`, trang
  ngoài app → `/`, Sales → `/sales/orders`), `visibility.test.ts`
  (`supportStaffOnly`). Gỡ nhánh lọc `supportStaffOnly`, gỡ header, gỡ đóng
  quyền khi `support_grant_ended`, gỡ kiểm trang trong app, gỡ tenant của
  quyền → mỗi lần một test đỏ. Toàn bộ vitest web: 342 xanh; `pnpm lint`,
  `pnpm typecheck` xanh; `next build` biên dịch và sinh 29 trang, bước chép
  `standalone` lỗi `EPERM symlink` trên Windows (quyền tạo symlink của máy,
  không phải mã; CI build trên Linux).
- `reviewing-deployment-security`: header mới đã có trong `_CORS_HEADERS`
  (ticket 02); token không lưu thêm ở đâu; quyền chỉ ở `sessionStorage`
  (hết khi đóng tab); trang `/support` không đọc gì ngoài `GET
/support/my-grants` (danh tính, chỉ nhân viên hỗ trợ); không image, không
  secret, không URL ra ngoài.
- **Playwright: viết, chưa chạy.** `apps/web/e2e/support-session.spec.ts`:
  bật `support_access` cho tenant-alpha, tạo một nhân viên hỗ trợ, Giang cấp
  bộ của Sales và Chi (người vận hành) giao, đều qua API; nhân viên với token
  dev hai lớp thấy quyền ở `/support`, bấm "Mở" tới `/sales/orders`, request
  kế tiếp mang mã quyền và tenant của quyền, băng hiện, "Thoát quyền hỗ trợ"
  về `/support`; token không có yếu tố thứ hai → trang chặn. Docker Desktop
  (WSL, `Wsl/CO_E_SERVER_EXEC_FAILURE`) ngừng trả lời lúc 22:00 13/10/2026,
  giữa lượt integration, và không lên lại sau 20 phút chờ; agent không khởi
  động lại WSL (dịch vụ của máy, dùng chung với dự án khác). Còn nợ khi
  Docker lên lại: `make db-migrate`, `make demo-reset`, rồi
  `pnpm --filter @dw/web exec playwright test e2e/support-session.spec.ts`;
  thêm vào `playwright.config.ts` các project 320px, 992px, 1440px tối và
  múi giờ Los Angeles cho spec này (cấu hình chưa có project
  `tz-los-angeles` của antd-shell ticket 05).
