# 10 — CI chạy test web

Status: needs-info (Đạt còn nợ quyết định "CI có chạy vitest của web không", `.claude/PLAN.md`)
Blocked by: 05
Area: web-ui

## Mục tiêu

Test của S0 chạy ở nơi mọi thay đổi đều đi qua. Hôm nay job `frontend-quality` trong
`.github/workflows/ci.yml` chạy Prettier, lint, typecheck và build web, nhưng không
chạy vitest hay Playwright. Vì vậy test layer của 02 và mọi chốt của 03–09 chỉ chạy
trên máy người làm, đúng hình `failure-modes.md` #1: khai ra mà không ai chạy.

## Cần Đạt chốt

- **(a) Khuyến nghị.** Không cần API, Postgres hay Keycloak, vì fixture không gọi API.
  Ước tính thêm vài phút mỗi lượt chạy; đo khi làm. Thêm vào `frontend-quality`:
    - `pnpm run test` (turbo gom vitest của `@dw/web` và `@dw/ui`);
    - `pnpm --filter @dw/web test:tz`;
    - Playwright các spec `@ui` và `@tz` trên bản dev-auth (`next build` với
      `NEXT_PUBLIC_AUTH_MODE=dev`, rồi `next start`), mọi project bề rộng và project múi
      giờ.
- **(b)** Chỉ thêm vitest, Playwright vẫn chạy tay. Rẻ hơn, nhưng thứ tự layer, bề rộng
  và múi giờ lại chỉ được tin.
- **(c)** Không thêm gì. Test S0 chỉ chạy trên máy người làm.

Spec cần API (`feedback.spec.ts`) không thuộc ticket này dưới cả ba phương án.

## Việc cần làm (nếu chọn a)

- `.github/workflows/ci.yml`, job `frontend-quality`: cài trình duyệt Playwright
  (`pnpm --filter @dw/web exec playwright install --with-deps chromium`), các bước ở
  trên; lưu báo cáo HTML khi đỏ.
- `apps/web/playwright.config.ts`: khi `CI` có giá trị, `webServer` chạy
  `pnpm start` trên bản đã build, không `pnpm dev`.
- Ghi vào `.claude/plans/web-ui.md` mục Open rằng web tests đã vào CI; gỡ dòng "The web
  vitest suite is not run by CI".

## Tiêu chí chấp nhận

- [ ] Một PR thử làm hỏng một test vitest của `lib/dates.ts`: job `frontend-quality` đỏ.
- [ ] Một PR thử xóa dòng `@layer …` trong `globals.css`: job đỏ ở
      `e2e/antd-shell.spec.ts`.
- [ ] Một PR thử thêm phần tử rộng 400px vào fixture: job đỏ ở project `phone-320`.
- [ ] Ba PR thử đó không merge; ghi link lượt chạy đỏ dưới Comments.
- [ ] Trên `main`, job xanh, thời gian thêm ghi trong `web-ui.md`.

## Nguồn

- `.claude/PLAN.md`, mục "Decisions Đạt owes" › Runtime: "whether CI runs the web vitest
  suite".
- `.claude/plans/web-ui.md` mục Open: "The web vitest suite is not run by CI".
- `ui-quality.md` mục "How it is checked" (nhánh `bidding`): layer test, project bề rộng
  và múi giờ, web tests trong CI đều đang nợ.
- `failure-modes.md` #1 (bước CI khai ra mà không chạy gì, lần thứ mười), #3.
- Spec, Câu hỏi còn mở 1.

## Comments
