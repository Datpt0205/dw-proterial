# 16 — Ô Sáng / Tối / Theo máy (P1)

Status: needs-info
Blocked by: 15
Area: web-ui

## Mục tiêu

Người dùng tự chọn Sáng, Tối hoặc Theo máy trong menu người dùng, như design vẽ.
Mặc định là Theo máy, đúng hành vi hôm nay. Ticket P1: không chặn slice.

## Cần Đạt chốt

Design vẽ ô này trong menu người dùng, kèm ghi chú "(chờ D07)"; D07 chốt "sáng/tối
theo máy như design" (spec, Câu hỏi còn mở 6). Có làm ô chọn không?

- **Có:** làm theo dưới đây.
- **Không:** đặt ticket `wontfix`, gỡ dòng P1 ở spec và ghi quyết định vào
  `.claude/plans/web-ui.md`.

## Việc cần làm (nếu có)

- `packages/typescript/ui/src/theme-provider.tsx`: nhận chế độ `light | dark | system`;
  `system` giữ hành vi hôm nay. Một hook `useColorMode()` trả chế độ đang chọn và hàm
  đổi; chỉ `ThemeProvider` giữ giá trị này.
- Lựa chọn là tiện ích của từng người xem, không phải dữ liệu cần giữ chắc: lưu ở
  trình duyệt bằng cơ chế trước khi vẽ của ticket 15 (để người chọn Tối trên máy Sáng
  cũng không thấy nháy), đọc và ghi trong `try/catch`, đọc không được thì `system`.
- Menu người dùng (`apps/web/components/session-chip.tsx`): một `Segmented` "Sáng /
  Tối / Theo máy" có nhãn đọc được.

## Tiêu chí chấp nhận

- [ ] Playwright `@ui`: máy ở chế độ sáng, chọn "Tối" thì nền trang thành
      `rgb(0, 0, 0)`; tải lại trang thì vẫn tối ngay lần vẽ đầu (cùng cách đo của 15).
- [ ] Playwright `@ui`: chọn "Theo máy" rồi đổi `colorScheme` của trang thì theme đổi theo.
- [ ] Vitest: kho lưu ném lỗi khi đọc thì chế độ là `system` và trang không vỡ.
- [ ] `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Khung" (menu người dùng) và Câu hỏi còn mở 6.
- D07 (Đạt 2/10/2026).
- Ticket 15.

## Comments
