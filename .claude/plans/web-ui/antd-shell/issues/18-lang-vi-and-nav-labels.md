# 18 — `lang="vi"` và nhãn menu nền tảng

Status: needs-info
Blocked by: 02
Area: web-ui

## Mục tiêu

Trình đọc màn hình đọc trang bằng giọng tiếng Việt, và menu không lẫn hai thứ tiếng.
Hôm nay `apps/web/app/layout.tsx` đặt `<html lang="en">` trong khi locale antd là
`vi_VN`, và nhãn menu nền tảng trong `apps/web/lib/nav/registry.ts` là tiếng Anh
("Home", "Approvals", "Audit log", "Roles & access"…).

## Cần Đạt chốt

Spec, Câu hỏi còn mở 4: ai dịch trang nền tảng, lúc nào? Khuyến nghị: ticket này chỉ đổi
`lang` và dịch nhãn menu nền tảng, trước buổi demo. Nội dung từng trang nền tảng dịch
khi trang đó được dựng lại trên antd, không quét một lượt. Đổi `lang="vi"` khi nội dung
trang còn tiếng Anh làm trình đọc màn hình đọc chữ Anh bằng giọng Việt, nên hai việc đi
cùng nhau hoặc không làm.

## Việc cần làm (nếu theo khuyến nghị)

- `apps/web/app/layout.tsx`: `<html lang="vi">`.
- `apps/web/lib/nav/registry.ts`: dịch 13 nhãn menu nền tảng; chữ do Đạt duyệt, ghi bảng
  chữ cũ và mới dưới Comments.
- Trang nền tảng còn chữ tiếng Anh: khối chữ đó mang `lang="en"` cho tới khi được dịch,
  để trình đọc màn hình đọc đúng.
- Sửa test e2e đang tìm theo nhãn tiếng Anh.

## Tiêu chí chấp nhận

- [ ] Playwright `@ui`: `document.documentElement.lang` là `vi`.
- [ ] Vitest: không nhãn nào trong `registry.ts` trùng chữ tiếng Anh cũ (danh sách cũ
      chép trong test).
- [ ] `pnpm run lint`, `pnpm run typecheck`, `pnpm --filter @dw/web build` xanh.

## Nguồn

- Spec, Câu hỏi còn mở 4.
- `.claude/plans/web-ui.md` mục Open (`<html lang="en">` trong khi locale là `vi_VN`).
- Ticket 02, mục Comments.
- `ui-quality.md` §12 (mọi điều khiển có tên đọc được bằng ngôn ngữ của màn) (nhánh
  `bidding`).

## Comments
