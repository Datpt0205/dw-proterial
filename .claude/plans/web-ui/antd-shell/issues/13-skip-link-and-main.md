# 13 — Bỏ qua tới nội dung chính, vùng `main`

Status: ready-for-agent
Blocked by: 05
Area: web-ui

## Mục tiêu

Người dùng bàn phím và trình đọc màn hình vào thẳng nội dung, không phải Tab qua thương
hiệu, workspace, cả menu và các nút bên phải ở mỗi trang (WCAG 2.4.1). Vùng nội dung
có đệm đúng design. Hôm nay `AppShell` không có liên kết bỏ qua, và `Layout.Content`
không có `id` hay `tabIndex`, đệm là `px-3 py-4 sm:px-4 sm:py-5`.

## Việc cần làm

- `packages/typescript/ui/src/app-shell.tsx`:
    - phần tử focus được đầu tiên là `<a href="#main">Bỏ qua tới nội dung chính</a>`,
      ẩn khỏi mắt tới khi nhận focus, khi focus thì hiện ở góc trên trái, trên header,
      đủ tương phản (spec mục "Khung");
    - `Layout.Content` thành `<main id="main" tabIndex={-1}>` (đo xem antd 6.6.5 vẽ
      `Layout.Content` thành `main` chưa; nếu rồi thì chỉ thêm `id` và `tabIndex`, không
      lồng `main` trong `main`);
    - bấm liên kết thì focus vào `main` (không chỉ cuộn), kể cả khi Next.js giữ URL;
    - đệm của `main` theo spec: 24px 28px 80px từ 992px, 16px 14px 80px dưới 992px,
      bằng lớp bố cục Tailwind (đệm là bố cục, `CLAUDE.md` "Web UI").
- Chữ của liên kết vào `AppShell` qua một prop bắt buộc (`skipLabel`), như `navLabel`
  và `menuLabel` hôm nay; `app-frame.tsx` truyền "Bỏ qua tới nội dung chính".
- `scroll-padding-top` của trang bằng chiều cao header, để focus vào phần tử dưới header
  dính không bị che (WCAG 2.4.11).

## Tiêu chí chấp nhận

- [ ] Playwright `@ui` trên `/dev-login/ui-kit`, mọi project bề rộng: Tab đầu tiên
      focus vào liên kết "Bỏ qua tới nội dung chính" và liên kết hiện trong khung nhìn
      (hộp bao rộng hơn 1px); Enter thì `document.activeElement` là `main#main`. Gỡ
      liên kết thì Tab đầu tiên rơi vào phần tử khác và test đỏ.
- [ ] Playwright `@ui`: chưa nhấn Tab thì liên kết không hiện (không chiếm chỗ, không
      che thương hiệu).
- [ ] Vitest `@dw/ui`: `AppShell` có đúng một `main` với `id="main"`.
- [ ] Playwright `@ui`: đệm của `main` ở `desktop-1280` là 24px 28px 80px, ở `phone-390`
      là 16px 14px 80px.
- [ ] `pnpm --filter @dw/ui test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Khung" (bỏ qua tới nội dung chính, vùng nội dung).
- `ui-quality.md` §12 (tên đọc được, thanh dính không che phần tử đang focus) (nhánh
  `bidding`).
- Spec, Ngoài phạm vi trước 3/10/2026 ghi mục này là P1; chuyển vào phạm vi vì là yêu
  cầu truy cập.

## Comments
