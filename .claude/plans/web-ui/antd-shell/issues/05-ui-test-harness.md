# 05 — Hạ tầng kiểm thử UI: bề rộng, múi giờ, fixture

Status: ready-for-agent
Blocked by: 02, 03
Area: web-ui

## Mục tiêu

Những gì S0 hứa về bề rộng và múi giờ được test, không phải được tin. Hôm nay
`apps/web/playwright.config.ts` chỉ có một project Desktop Chrome, múi giờ lấy theo máy
chạy (máy Đạt ở +07, runner CI ở UTC), và `@dw/ui` không có test nào.

## Việc cần làm

- `apps/web/playwright.config.ts` là chủ duy nhất của danh sách bề rộng:
    - `phone-320` (320×640, `hasTouch`), `phone-390` (390×844, `hasTouch`),
      `narrow-991` (991×800), `wide-992` (992×800), `desktop-1280` (1280×800, thay project
      `chromium` hiện có).
    - `tz-los-angeles`: như `desktop-1280`, `timezoneId: "America/Los_Angeles"`.
    - Mọi project khác đặt rõ `timezoneId: "Asia/Ho_Chi_Minh"`, để máy dev và CI chạy
      như nhau; giữ `locale: "vi-VN"`.
    - Spec gắn thẻ `@ui` (chỉ dùng fixture, không cần API) chạy ở mọi project bề rộng;
      spec gắn `@tz` chạy ở `tz-los-angeles` và `desktop-1280`; `feedback.spec.ts` (cần
      API) chỉ chạy ở `desktop-1280`. Dùng `grep`/`grepInvert` theo project.
- Fixture `apps/web/app/dev-login/ui-kit/page.tsx`, theo mẫu `layer-check` của 02: chỉ
  ở bản dev-auth (`AUTH_MODE !== "dev"` thì `notFound()`), không gọi API, dữ liệu là
  hằng cố định (không `Date.now()`). Bọc trong `AppShell`. Mục đầu tiên: giờ (mọi dạng
  của 03, cùng các ca biên) và tiền (04 nếu đã xong). Ticket 07–09 thêm mục của mình.
- `apps/web/components/app-frame.tsx`: cho fixture mới đi qua cổng đăng nhập, chỉ ở
  chế độ dev, cùng điều kiện với `layer-check`.
- `packages/typescript/ui`: thêm script `test` (vitest, jsdom,
  `@testing-library/react`, cùng phiên bản đã ghim ở `apps/web`) và
  `vitest.config.mts`; `turbo run test` gom được nó. Một test khói cho `AppShell` để
  chứng minh bộ chạy thật sự chạy.
- `e2e/ui-kit.spec.ts` với các test dưới đây.

## Tiêu chí chấp nhận

- [ ] Ở mọi project bề rộng, `/dev-login/ui-kit` và `/dev-login/layer-check` không cuộn
      ngang: `document.documentElement.scrollWidth <= window.innerWidth`. Thêm một phần tử
      rộng 400px vào fixture thì test đỏ ở `phone-320`.
- [ ] Dưới 992px có nút "Mở menu" (vùng chạm ít nhất 24×24) mở ngăn kéo; từ 992px có
      menu ngang và không có nút đó.
- [ ] `@tz`: ở `tz-los-angeles` và `desktop-1280`, thời điểm `2026-10-14T02:00:00Z`
      trên fixture hiện `09:00 14/10/2026 (giờ Việt Nam)` và ngày `2026-10-14` hiện
      `14/10/2026`. Thay `lib/dates.ts` bằng bản dùng giờ của trình duyệt thì test đỏ ở
      `tz-los-angeles` (ghi kết quả dưới Comments).
- [ ] Vitest: với `AUTH_MODE` là `oidc`, trang fixture gọi `notFound()` và `AppFrame`
      không cho đường dẫn fixture đi qua cổng đăng nhập. Bỏ điều kiện chế độ dev thì test
      đỏ.
- [ ] `pnpm --filter @dw/ui test` chạy và xanh; làm hỏng test khói thì lệnh đỏ.
- [ ] `pnpm --filter @dw/web e2e --grep @ui` xanh khi không có API chạy.
- [ ] Chạy `reviewing-deployment-security` cho đường fixture mới; ghi kết luận dưới
      Comments.

## Nguồn

- Spec, mục "Màn hình" (fixture là bản code của `#catalog`, `V3Catalog.dc.html`).
- `ui-quality.md` §12 (nhánh `bidding`): danh sách bề rộng một chủ, ít nhất 320px, hai
  phía 992px, một project múi giờ khác Việt Nam.
- Design v3 `doi-chieu-codebase.md` mục "Kiểm thử" (project theo bề rộng 320px, hai
  phía 992px, một project múi giờ khác).
- Ticket 02 (`layer-check`, `e2e/antd-shell.spec.ts`), ticket 03.
- `failure-modes.md` #3 (bộ test mới xanh ngay lần đầu là lý do để kiểm nó).

## Comments
