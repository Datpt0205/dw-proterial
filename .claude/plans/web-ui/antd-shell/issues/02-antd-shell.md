# 02 — Shell antd: theme A, provider, AppShell, thứ tự layer

Status: resolved
Blocked by: 01
Area: web-ui

Một agent khác đang làm ticket này trong worktree `codebase-main` (2/10/2026). Không
sửa code của nó; góp ý ghi dưới `## Comments`.

## Mục tiêu

Web chạy trên antd v6 với một theme do `@dw/ui` giữ, khung menu ngang của design v3,
và một test bắt được thứ tự layer sai. Đây là lát đầu của quyết định 28/9 trong
`CLAUDE.md` "Web UI".

## Việc cần làm

- Phụ thuộc: `antd` ^6.6.5, `@ant-design/icons`, `@ant-design/nextjs-registry`,
  `dayjs` trong `apps/web/package.json` và `packages/typescript/ui/package.json`;
  `pnpm-lock.yaml`.
- `packages/typescript/ui/src/theme.ts`: theme bảng màu A sáng và tối (spec, mục
  "Token bảng màu A"), `cssVar` với lớp `css-var-dw`.
- `packages/typescript/ui/src/theme-provider.tsx`: `ConfigProvider` với `vi_VN`,
  `theme.darkAlgorithm` khi máy ở chế độ tối, `<App>` của antd, `dayjs.locale("vi")`.
- `packages/typescript/ui/src/app-shell.tsx`: header 56px dính, menu ngang từ 992px,
  `Drawer` trái dưới 992px, mục hiện tại `aria-current="page"`.
- `apps/web/app/layout.tsx`: `AntdRegistry layer`, lớp theme trên `<html>`, phông.
- `apps/web/app/globals.css`: `@layer theme, base, antd, components, utilities;` trước
  `@import "tailwindcss"`; màu Tailwind là tên của biến `--ant-*`; `--breakpoint-*`
  bằng antd.
- `apps/web/components/app-frame.tsx` dùng `AppShell`; `nav-links.tsx` bị gỡ.
- Fixture `apps/web/app/dev-login/layer-check/page.tsx` (chỉ bản dev-auth) và
  `apps/web/e2e/antd-shell.spec.ts`.
- Đo bundle trước và sau trên app này, ghi vào `.claude/plans/web-ui.md`.

## Tiêu chí chấp nhận

- [ ] `e2e/antd-shell.spec.ts` xanh; xóa dòng `@layer …` trong `globals.css` thì test
      "a Tailwind utility beats antd" đỏ (ghi kết quả dưới Comments).
- [ ] Ở 991px có nút "Mở menu" và lớp `lg:` của Tailwind ẩn; ở 992px có menu ngang và
      lớp `lg:` hiện. Đổi `--breakpoint-lg` thì test đỏ.
- [ ] Theme theo chế độ màu của máy, cả hai chiều (`page.emulateMedia`).
- [ ] Mọi biến `--ant-*` mà `globals.css` gọi tên đều có giá trị trên `<html>`.
- [ ] `/dev-login/layer-check` trả 404 ở bản `oidc`.
- [ ] `pnpm run lint`, `pnpm run typecheck`, `pnpm --filter @dw/web build` xanh.
- [ ] Bundle first-load JS trước/sau theo route ghi trong `web-ui.md`, so với mức
      +250 kB đã chấp nhận.

## Nguồn

- `CLAUDE.md` "Web UI"; `.claude/plans/web-ui.md` (Decision 28/9, Open).
- Design v3 `EHSDT v3.dc.html` (khung, token), `V3Catalog.dc.html` (bảng token).
- D07 (Đạt 2/10/2026: theo design v3, bảng màu A, sáng/tối theo máy, shell trên `main`
  trước).
- `ui-quality.md` §1, §12 (nhánh `bidding`).

## Comments

- **2/10/2026, người viết spec S0, đối chiếu bản đang làm với design v3.** Để người làm
  02 cân nhắc; mục nào 02 không làm thì ticket 07 làm, và test tương phản của 07 sẽ bắt
  phần màu.
    - Theme tối đặt `colorError: "#ff453a"`: chữ trắng trên nút nguy hiểm chỉ đạt
      3,41:1. CSS khung v3 tách nền nút `#d63a30` (4,66:1) với chữ lỗi `#ff6b61`; antd có
      `colorErrorText` cho phần chữ.
    - `borderRadius: 8`, `borderRadiusLG: 12` khác design: nút viên thuốc, trường 11px,
      thẻ 20px, hộp thoại và Drawer 24px.
    - Cỡ nút nhỏ của design là 28px (`controlHeightSM` mặc định 24).
    - Họ chữ: design đặt phông hệ thống Apple trước Be Vietnam Pro; bản đang làm đặt Be
      Vietnam Pro trước. Trên Windows hai cách cho cùng kết quả.
    - `<html lang="en">` vẫn giữ trong khi locale là `vi_VN` (spec, Câu hỏi còn mở 4).
