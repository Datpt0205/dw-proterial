# 06 — Thông báo qua `App.useApp()`, gỡ sonner

Status: ready-for-agent
Blocked by: 02, 05
Area: web-ui

## Mục tiêu

Mọi thông báo nổi và hộp xác nhận đi qua `App.useApp()` của antd, đọc theme và
`vi_VN`. Thông báo lỗi in câu của server, không in mã máy. Hôm nay sonner phát thông
báo ở 4 tệp, và `useCachedResource` in `failure.message`, tức `"permission_denied: …"`.

## Việc cần làm

- Cấu hình mặc định một lần trên `<App>` trong
  `packages/typescript/ui/src/theme-provider.tsx`: `notification` ở đáy giữa
  (`placement: "bottom"`), tối đa 3; `message` tối đa 3.
- Quy ước (ghi trong chú thích của `theme-provider.tsx`, theo spec mục "Khung"):
    - thông báo có tiêu đề và mô tả dùng `notification`;
    - thành công và thông tin tự tắt sau 4,2 giây;
    - có nút Hoàn tác thì 7 giây, và chỉ khi server hoàn tác thật;
    - lỗi có nút "Thử lại" thì `duration: 0`, kèm "Mã yêu cầu: {request_id}" khi có;
    - xác nhận dùng `modal.confirm` với nút OK `danger` và `autoFocusButton: "cancel"`.
- Thay sonner ở năm tệp dưới đây. Giữ nguyên chữ của từng thông báo, chỉ đổi kênh;
  dịch không thuộc ticket này.
    - `apps/web/app/layout.tsx` (gỡ `<Toaster>`);
    - `apps/web/app/platform/page.tsx` (12 chỗ);
    - `apps/web/components/feedback/dialog.tsx` (2 chỗ);
    - `apps/web/lib/use-cached-resource.ts`;
    - `apps/web/lib/use-cached-pages.ts`.
- `useCachedResource` và `useCachedPages` gọi `App.useApp()` bên trong hook; câu lỗi
  lấy từ `errorMessage()` (`apps/web/lib/error-message.ts`).
- Thêm mục "Thông báo" vào fixture `/dev-login/ui-kit` của 05: mỗi loại một nút phát
  thử (thành công, lỗi có "Thử lại", có Hoàn tác, hộp xác nhận).
- Sửa `apps/web/lib/__tests__/use-cached-pages.test.tsx` (đang mock `sonner`).
- Gỡ `sonner` khỏi `apps/web/package.json` và lockfile.
- Luật ESLint trong `apps/web/.eslintrc.json`:
    - `no-restricted-imports` cấm `sonner`;
    - cấm import tên `message`, `notification` từ `antd` (bản tĩnh không đọc theme);
    - `no-restricted-syntax` cấm `Modal.confirm`, `Modal.info`, `Modal.success`,
      `Modal.error`, `Modal.warning` tĩnh.

## Tiêu chí chấp nhận

- [ ] Vitest: render một component dùng `useCachedResource` trong `<App>`; `load` ném
      một `ApiError` status 403, `code` là `permission_denied`, `message` là "Bạn không
      có quyền xem mục này", `request_id` là `req_1`. DOM có "Bạn không có quyền xem
      mục này", không có `permission_denied:`. Đổi lại thành `failure.message` thì test
      đỏ.
- [ ] Vitest: thông báo lỗi có nút "Thử lại" vẫn còn sau khi chạy hết hẹn giờ giả
      (`vi.advanceTimersByTime(10_000)`); thông báo thành công thì đã tắt.
- [ ] Vitest: phát 4 thông báo liền nhau thì DOM chỉ còn 3.
- [ ] Một test chạy ESLint (`ESLint#lintText`) trên bốn đoạn:
    - `import { toast } from "sonner"` ra lỗi đúng luật;
    - `import { message } from "antd"` ra lỗi đúng luật;
    - `Modal.confirm({})` ra lỗi đúng luật;
    - `const { message } = App.useApp()` không ra lỗi.
- [ ] `grep -rn "sonner" apps/web --include=*.ts --include=*.tsx` (bỏ `node_modules`)
      không còn kết quả; `pnpm why sonner --filter @dw/web` không còn.
- [ ] Playwright `@ui` trên fixture `/dev-login/ui-kit`: bấm nút thử phát thông báo
      thì nó hiện ở nửa dưới màn hình, có `role` để trình đọc màn hình đọc được.
- [ ] `pnpm run lint`, `pnpm run typecheck`, `pnpm --filter @dw/web test` xanh.

## Nguồn

- Spec, mục "Khung" (thông báo nổi, hộp xác nhận) và luồng "Thông báo".
- Design v3 `README.md` bảng "Map sang antd v6": toast giữa đáy →
  `App.useApp().message` / `notification`, tối đa 3, Hoàn tác 7 giây chỉ khi server
  hoàn tác thật; hộp xác nhận focus vào Hủy.
- `ui-quality.md` §1 (một chủ cho thông báo), §4 (câu của server qua `errorMessage()`),
  §10 (xác nhận focus vào Hủy) (nhánh `bidding`).
- `apps/web/lib/error-message.ts` (chú thích giải thích vì sao không in mã máy).

## Comments
