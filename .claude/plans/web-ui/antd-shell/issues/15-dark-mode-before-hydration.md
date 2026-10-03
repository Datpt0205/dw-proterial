# 15 — Chế độ tối không nháy sáng khi tải

Status: ready-for-agent
Blocked by: 05
Area: web-ui

## Mục tiêu

Máy ở chế độ tối thấy trang tối ngay từ lần vẽ đầu, không thấy trang sáng rồi mới đổi.

Hôm nay server không biết chế độ màu của máy nên vẽ sáng; `ThemeProvider` đổi sang tối
ở lần render đầu phía trình duyệt (`useSyncExternalStore`, `onServer = () => false`).
`.claude/plans/web-ui.md` mục Open ghi đo được: trên `next dev` nền trang đọc
`rgb(245, 245, 247)` trước khi thành đen; trên `next start` hydrate đến trước lần đọc
đầu. Một khối `@media (prefers-color-scheme: dark)` cho biến `--ant-*` chung là không
đủ, vì antd phát token của từng component thành giá trị cụ thể (HTML của SSR có
`--ant-layout-header-bg:#ffffff`, `--ant-menu-item-selected-bg:#e6f7ff`, không
`var()`), nên header và menu vẫn sáng.

## Việc cần làm

- Đo hai hướng trên bản `next build` + `next start` (`failure-modes.md` #4), ghi số đo
  và lựa chọn dưới Comments:
    - **(a)** CSS của cả hai theme có sẵn trong HTML của SSR, bản tối nằm trong
      `@media (prefers-color-scheme: dark)`, gồm cả token của component. Đo xem antd
      6.6.5 có cách phát CSS của theme tối lúc SSR không (ví dụ một `cssVar.key` riêng
      cho theme tối), và bundle thêm bao nhiêu.
    - **(b)** Một tín hiệu server đọc được trước khi vẽ (cookie hoặc client hint
      `Sec-CH-Prefers-Color-Scheme`). Mọi route thành động; đo thời gian phản hồi và ghi
      đó là giá phải trả.
- Chọn hướng rẻ hơn mà đạt tiêu chí dưới đây. Hướng (b) đổi cách render của mọi trang,
  nên ghi lý do vào `.claude/plans/web-ui.md` (Decision) trước khi merge.
- Ticket 16 (ô Sáng / Tối / Theo máy, nếu Đạt chọn có) dựng trên cơ chế này, nên cơ
  chế không được giả định chỉ có "theo máy".
- Gỡ mục "The server renders light…" khỏi `web-ui.md` mục Open khi xong.

## Tiêu chí chấp nhận

- [ ] Playwright `@ui` trên bản đã build, `colorScheme: "dark"`, `javaScriptEnabled: false`,
      mở `/dev-login/layer-check`: nền `body` là `rgb(0, 0, 0)` và nền header không phải
      `rgb(255, 255, 255)`. Hôm nay test này đỏ; ghi lượt đỏ trước khi sửa dưới
      Comments.
- [ ] Cùng test (`@ui`) với `colorScheme: "light"`: nền `body` là `rgb(245, 245, 247)`.
- [ ] Playwright `@ui`, bật JS lại: sau hydrate, màu header và menu giống hệt lúc chưa hydrate ở cả hai chế
      độ (không đổi màu sau lần vẽ đầu).
- [ ] Bundle first-load JS và, nếu chọn (b), thời gian phản hồi của trang chủ trước/sau
      ghi trong `web-ui.md`.
- [ ] `pnpm run lint`, `pnpm run typecheck`, `pnpm --filter @dw/web build` xanh.

## Nguồn

- Spec, mục "Mục tiêu" (sáng hoặc tối theo máy) và Câu hỏi còn mở 6.
- `.claude/plans/web-ui.md` mục Open (nháy sáng khi tải, token component của antd).
- `packages/typescript/ui/src/theme-provider.tsx` (`onServer`).
- D07 (Đạt 2/10/2026): sáng/tối theo máy như design.
- `failure-modes.md` #3 (test phải đỏ trước khi sửa), #4.

## Comments
