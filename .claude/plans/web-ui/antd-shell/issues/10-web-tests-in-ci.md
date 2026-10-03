# 10 — CI chạy test web

Status: needs-info
Blocked by: 05
Area: web-ui

## Mục tiêu

Test của S0 chạy ở nơi mọi thay đổi đều đi qua. Hôm nay job `frontend-quality` trong
`.github/workflows/ci.yml` chạy Prettier, lint, typecheck và build web, nhưng không
chạy vitest hay Playwright. Vì vậy test layer của 02 và mọi chốt của 03–09 chỉ chạy
trên máy người làm, đúng hình `failure-modes.md` #1: khai ra mà không ai chạy.

Spec Playwright cần API cũng vậy. Hôm nay chỉ có `feedback.spec.ts`, nhưng mọi context
dựng màn trên nền tảng sẽ thêm test âm ở mức giao diện cần stack thật: trường bị ẩn
không có trong DOM lẫn trong phản hồi mạng, gỡ `disabled` trên nút thì server vẫn từ
chối. Không chạy ở CI thì các chốt đó cũng chỉ là lời khai.

## Cần Đạt chốt

Câu 1, spec fixture (không cần API):

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

Câu 2, spec cần API (gắn `@api`, ticket 05):

- **(d) Khuyến nghị.** Một job mới `web-e2e-api`, chạy trên push và pull request như
  các job khác, `needs: [contracts]`. Dựng stack bằng compose profile `full` với
  `DW_API_AUTH_MODE=dev`, `DW_API_DEV_SECRET` (`.env.example` có sẵn),
  `NEXT_PUBLIC_AUTH_MODE=dev` (nướng lúc build ảnh web), `DW_API_PROFILE=test` (đăng
  nhập dev bị cấm ở profile triển khai, `settings.validate_for_profile`), chờ API và web như
  job `containers`, rồi `pnpm --filter @dw/web e2e --grep @api` với `E2E_WEB_URL` và
  `E2E_API_URL` trỏ vào stack. Job này tốn thời gian ngang job `containers`; đo khi làm.
- **(e)** Không thêm. Ghi rõ trong `web-ui.md` rằng test âm ở mức giao diện chỉ chạy tay,
  và mỗi chốt như vậy phải có test tích hợp API đứng thay ở phía server.

Một context thêm spec cần API chỉ gắn `@api`; không sửa workflow. Một thẻ là chủ duy
nhất của câu "spec này cần stack".

## Việc cần làm (nếu chọn a)

- `.github/workflows/ci.yml`, job `frontend-quality`: cài trình duyệt Playwright
  (`pnpm --filter @dw/web exec playwright install --with-deps chromium`), các bước ở
  trên; lưu báo cáo HTML khi đỏ.
- `apps/web/playwright.config.ts`: khi `CI` có giá trị, `webServer` chạy
  `pnpm start` trên bản đã build, không `pnpm dev`.
- Ghi vào `.claude/plans/web-ui.md` mục Open rằng web tests đã vào CI; gỡ dòng "The web
  vitest suite is not run by CI".

## Việc cần làm (nếu chọn d)

- Job `web-e2e-api` trong `.github/workflows/ci.yml` như trên. Dữ liệu mẫu là dữ liệu
  dev sẵn có của stack (người dùng dev mà `feedback.spec.ts` đăng nhập); đo xem compose
  `full` có nạp nó không trước khi dựa vào nó (`failure-modes.md` #4).
- `apps/web/playwright.config.ts` đã có `reuseExistingServer: true`, nên web của stack
  được dùng lại; kiểm rằng job không dựng thêm `pnpm dev`.
- Khi đỏ: lưu báo cáo HTML và log `api`, `web`, như job `containers`.
- Ghi vào `web-ui.md` mục Open thời gian thêm của job.

## Tiêu chí chấp nhận

- [ ] Một PR thử làm hỏng một test vitest của `lib/dates.ts`: job `frontend-quality` đỏ.
- [ ] Một PR thử xóa dòng `@layer …` trong `globals.css`: job đỏ ở
      `e2e/antd-shell.spec.ts`.
- [ ] Một PR thử thêm phần tử rộng 400px vào fixture: job đỏ ở project `phone-320`.
- [ ] Nếu chọn (d): một PR thử làm hỏng `feedback.spec.ts` (đổi chữ một nút nó bấm):
      job `web-e2e-api` đỏ; một spec `@api` mới thêm vào `e2e/` được job chạy mà không
      sửa workflow.
- [ ] Các PR thử đó không merge; ghi link lượt chạy đỏ dưới Comments.
- [ ] Trên `main`, các job xanh, thời gian thêm ghi trong `web-ui.md`.

## Nguồn

- `.claude/PLAN.md`, mục "Decisions Đạt owes" › Runtime: "whether CI runs the web vitest
  suite".
- `.claude/plans/web-ui.md` mục Open: "The web vitest suite is not run by CI".
- `ui-quality.md` mục "How it is checked" (nhánh `bidding`): layer test, project bề rộng
  và múi giờ, web tests trong CI đều đang nợ.
- `failure-modes.md` #1 (bước CI khai ra mà không chạy gì, lần thứ mười), #3.
- `.github/workflows/ci.yml` job `containers` (compose `full`, chờ bằng `curl --retry`).
- `apps/api/src/dw_api/settings.py` `validate_for_profile` (đăng nhập dev chỉ ở profile
  không triển khai).
- Spec, Câu hỏi còn mở 1.

## Comments

- **2/10/2026.** Đạt còn nợ quyết định "CI có chạy vitest của web không"
  (`.claude/PLAN.md`); dòng này trước nằm trên dòng Status.
- **3/10/2026, đối chiếu chéo.** Thêm câu 2 (spec `@api`): phương án (a) chỉ gom spec
  `@ui` và `@tz`, nên test âm ở mức giao diện của mọi context không chạy ở đâu.
