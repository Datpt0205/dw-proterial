# 09 — `RegionState` và băng mất mạng

Status: ready-for-agent
Blocked by: 03, 05, 07
Area: web-ui

## Mục tiêu

Mỗi trang và mỗi vùng tải dữ liệu riêng vẽ trạng thái của nó bằng một thành phần dùng
chung, và mã lỗi được ánh xạ sang trạng thái ở đúng một chỗ. Mất mạng được phát hiện
một lần trong shell, hiện thành băng dưới header; màn đọc trạng thái đó để khóa thao
tác ghi. Hôm nay mỗi trang tự vẽ lỗi, và `useCachedResource` chỉ phát một thông báo.

## Việc cần làm

- `packages/typescript/ui/src/region-state.tsx`, xuất từ `index.ts`:
    - Các kiểu, chữ mặc định và biểu tượng đúng bảng ở spec mục "Trạng thái vùng":
      `loading`, `empty`, `nomatch`, `search`, `partial`, `error`, `forbidden`,
      `notfound`, `conflict`, `entitlement`, `session`, `offline`, `stale`.
    - Dựng trên antd `Result` (biểu tượng tùy biến theo design), `Empty`, `Skeleton`. Hai
      cỡ: đầy đủ và gọn. `error` có `role="alert"`, còn lại `role="status"`.
    - Màn truyền được tiêu đề, mô tả, nút chính và nút phụ.
- Trong cùng tệp, bảng `ERROR_STATE` khai `satisfies Record<ErrorCodeValue, RegionKind>`.
  `ErrorCodeValue` lấy từ `@dw/contracts` (import kiểu; thêm `@dw/contracts` vào phụ
  thuộc của `@dw/ui`).
    - `permission_denied` → `forbidden`; `not_found` → `notfound`; `conflict` →
      `conflict`;
    - `entitlement_denied` → `entitlement`; `tenant_context_missing` → `session`;
    - mọi mã còn lại → `error`;
    - mã không có trong bảng (server mới hơn web) → `error`, không bao giờ hiện nội
      dung.
- `stateForError(input)` nhận `{ code, message, requestId? }` hoặc chuỗi `"offline"`, trả
  kiểu, câu của server và mã yêu cầu. Kiểu `error` hiện "Mã yêu cầu: {request_id}"
  bằng chữ mono.
- `apps/web/lib/error-message.ts`: thêm `toRegionError(error: unknown)` chuẩn hóa
  `ApiError` → `{ code, message: body.message, requestId: body.request_id }`. Lỗi
  `TypeError` của `fetch` khi `navigator.onLine === false` → `"offline"`. Lỗi khác →
  `{ code: "internal", message: errorMessage(error) }`.
- `packages/typescript/ui/src/network-status.tsx`:
    - `NetworkStatusProvider` nghe `online`/`offline` một lần, giữ
      `{ online: boolean, since: Date | null }`; hook `useNetworkStatus()`.
    - `ThemeProvider` hoặc `AppShell` gắn provider, để mọi trang có nó.
- `AppShell` (của 02) thêm băng mất mạng dính dưới header, `role="status"`, tông
  `warning`. Chữ do app truyền qua prop `offlineNotice: (since: Date) => ReactNode`,
  để giờ đi qua `lib/dates.ts`: "Mất kết nối lúc {formatInstant(since)}. Chưa có gì được
  gửi đi; dữ liệu bạn đã nhập vẫn giữ." `@dw/ui` không import `apps/web`.
- `apps/web/components/app-frame.tsx` truyền `offlineNotice`.
- Thêm mục "Trạng thái vùng" vào fixture `/dev-login/ui-kit`: mọi kiểu, hai cỡ, và một
  vùng giả lập lỗi từ một `ApiError` dựng sẵn cho từng mã.
- Không chuyển trang nền tảng nào sang `RegionState` trong ticket này; trang nào sửa
  lần sau thì chuyển.

## Tiêu chí chấp nhận

- [ ] Vitest duyệt `Object.values(ErrorCode)` từ `@dw/contracts`: mã nào cũng ra một
      kiểu đã định nghĩa. `permission_denied` → `forbidden`, `not_found` → `notfound`,
      `entitlement_denied` → `entitlement`. Đổi `entitlement_denied` thành `forbidden` thì
      test đỏ.
- [ ] tsc: bỏ một mã khỏi `ERROR_STATE` thì `pnpm run typecheck` đỏ (`satisfies`).
- [ ] Vitest: mã lạ `"brand_new_code"` → `error`.
- [ ] Vitest: `toRegionError(new TypeError("Failed to fetch"))` khi `navigator.onLine`
      là `false` → `offline`; khi `true` → `error`. Một `ApiError` → câu `body.message`,
      không có `"permission_denied:"`.
- [ ] Vitest: `error` hiện câu của server và "Mã yêu cầu: req_1"; có `role="alert"`.
- [ ] Playwright `@ui` trên fixture: `context.setOffline(true)` thì băng hiện dưới
      header, chữ có "(giờ Việt Nam)"; `setOffline(false)` thì băng mất. Ở `tz-los-angeles`
      giờ trong băng vẫn là giờ Việt Nam.
- [ ] Playwright `@ui`: ở `phone-320` mọi kiểu trên fixture không cuộn ngang.
- [ ] `pnpm --filter @dw/ui test`, `pnpm --filter @dw/web test`, `pnpm run lint`,
      `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Trạng thái vùng" (chép từ design v3 `V3State.dc.html`), "Khung" (băng mất
  mạng, chép từ `EHSDT v3.dc.html`), luồng "Lỗi thành trạng thái" và "Mất mạng".
- `ui-quality.md` §4 (bảng mã lỗi → trạng thái; 403 khác không tìm thấy;
  `entitlement_denied` không phải 403; lỗi mạng là mất mạng; phát hiện mất mạng một
  lần trong shell) (nhánh `bidding`).
- `CLAUDE.md` "Tenancy and authorization": kiểm quyền lợi gói và kiểm quyền là hai việc.
- `packages/typescript/contracts/src/error.ts`, `apps/api/src/dw_api/errors.py`
  (`_STATUS_BY_CODE`).
- Design v3 `doi-chieu-codebase.md` mục "Trạng thái vùng": một bảng `errorCode()` →
  403/404/conflict/500 trong thành phần trạng thái chung.

## Comments
