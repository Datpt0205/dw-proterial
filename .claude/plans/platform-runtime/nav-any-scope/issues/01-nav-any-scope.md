# 01 — `anyScope` và một hàm hiện mục menu

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Một mục menu hiện cho người có một trong nhiều scope, và luật hiện mục có đúng một chủ cho
cả menu lẫn trang đầu (spec, Hiện trạng).

## Việc cần làm

1. `apps/web/lib/nav/types.ts`: `NavItem` thêm `anyScope?: string[]` (doc comment: điều hướng,
   không phải phân quyền; API vẫn kiểm).
2. `apps/web/lib/nav/visibility.ts`: `isNavItemVisible(item, { isPlatformOperator, hasScope,
roles })` gồm `operatorOnly`, `scope`, `anyScope`, `roles`. Danh sách rỗng ở `anyScope` là
   lỗi cấu hình: hàm trả `false` (đóng khi sai, failure-modes #7).
3. `apps/web/components/app-frame.tsx` và `apps/web/app/page.tsx` gọi hàm đó, bỏ hai bộ lọc
   viết tay.

## Tiêu chí chấp nhận

- [ ] Vitest cho `isNavItemVisible`: mục có `anyScope` hiện với người có một scope trong danh
      sách, ẩn với người không có scope nào; có cả `scope` và `anyScope` thì cần cả hai;
      `anyScope: []` → ẩn; `operatorOnly`, `roles` giữ hành vi cũ. Gỡ nhánh `anyScope` → test
      đỏ.
- [ ] `rg "item.scope \|\| hasScope" apps/web` ra 0 chỗ ngoài `visibility.ts`.
- [ ] Menu và trang đầu không đổi với registry hiện có (Playwright hoặc vitest của
      `app-frame`).
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm build` xanh.

## Nguồn

- `apps/web/lib/nav/types.ts`, `registry.ts`; `apps/web/components/app-frame.tsx:42-50`;
  `apps/web/app/page.tsx:24-30`.

## Comments
