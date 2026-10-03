# 17 — Bảng lệnh Ctrl K (P1)

Status: ready-for-agent
Blocked by: 05
Area: web-ui

## Mục tiêu

Ctrl K (Cmd K trên Mac) mở một ô tìm để đi tới bất kỳ mục menu nào bằng bàn phím, như
design vẽ trong khung. Hữu ích khi menu ngang đã dồn mục vào "…" (ở 1280px một quản trị
tổ chức chỉ thấy ba mục, `.claude/plans/web-ui.md` mục Open). Ticket P1: không chặn
slice.

Bảng chỉ liệt kê mục menu (phần đề xuất của spec). Lệnh khác mà một context muốn thêm
là ticket sau, khi có nơi cần.

## Việc cần làm

- Một nguồn: bảng lấy đúng danh sách mục `app-frame.tsx` đưa cho `AppShell`
  (`visibleNav`, đã lọc theo scope). Không đọc `lib/nav/registry.ts` lần hai, để không
  có mục nào hiện trong bảng mà menu ẩn. Ẩn mục vẫn không phải phân quyền; route tự
  kiểm quyền như hôm nay.
- `packages/typescript/ui/src/command-palette.tsx`, xuất từ `index.ts`, trung tính:
  nhận `{ key, text }[]` và `onSelect(key)`; dựng trên antd `Modal` và `Input`, danh
  sách kết quả `role="listbox"`, mục đang chọn qua `aria-activedescendant`, mũi tên
  lên/xuống đổi mục, Enter chọn, Esc đóng và trả focus về chỗ cũ.
- Tìm không phân biệt hoa thường và dấu tiếng Việt ("duyet" tìm ra "Duyệt"), so trên
  `text` của mục.
- Phím tắt: Ctrl K trên Windows và Linux, Cmd K trên Mac; `preventDefault` để trình
  duyệt không chiếm phím (đo trên Chrome, Edge, Firefox); bỏ qua khi `isComposing` để
  Telex không mở bảng giữa chừng. Header có một nút mở bảng, chữ ghi "Ctrl K" trên
  Windows, để phím tắt luôn có điều khiển nhìn thấy được.
- Mục "Bảng lệnh" trên fixture `/dev-login/ui-kit` với danh sách mục mẫu trung tính.

## Tiêu chí chấp nhận

- [ ] Vitest `@dw/ui`: gõ "duyet" thì danh sách còn đúng mục "Duyệt"; Enter gọi
      `onSelect` với key của mục; Esc đóng và focus trở lại nút mở.
- [ ] Vitest `apps/web`: mục bị lọc khỏi menu vì thiếu scope cũng không có trong bảng
      (cùng danh sách); đổi bảng sang đọc registry chưa lọc thì test đỏ.
- [ ] Vitest: phím K khi `isComposing` là `true` không mở bảng.
- [ ] Playwright `@ui` trên fixture: Ctrl K mở bảng, gõ, Enter đi tới mục; ở `phone-390`
      nút mở bảng có vùng chạm ít nhất 24×24 và bảng không cuộn ngang.
- [ ] `pnpm --filter @dw/ui test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Khung" (bảng lệnh) và Ngoài phạm vi (P1).
- `ui-quality.md` §3 (phím tắt ghi Ctrl trên Windows, luôn có điều khiển nhìn thấy, bỏ
  qua khi `isComposing`) (nhánh `bidding`).
- `apps/web/components/app-frame.tsx` (`visibleNav`), `.claude/plans/web-ui.md` mục Open
  (menu dồn vào "…" sớm).
- `failure-modes.md` #2 (danh sách mục một chủ), #4.

## Comments
