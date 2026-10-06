# 01 — Liên kết sang hộp duyệt của context trên `/approvals`

Status: ready-for-agent
Blocked by: .claude/plans/web-ui/antd-shell/issues/03-lib-dates.md, .claude/plans/web-ui/antd-shell/issues/05-ui-test-harness.md
Area: platform-runtime

## Mục tiêu

Approval có tiền tố mà một context đã khai hộp riêng thì `/approvals` hiện một liên kết sang
hộp đó thay cho nút quyết (spec, Mục tiêu). Một cửa quyết trên web cho mỗi approval.

## Việc cần làm

1. `apps/web/lib/approvals/types.ts`: `ApprovalHost` thêm
   `inbox?: { label: string; href: (approval: Approval) => string }`; `client` thành
   `client?: () => ApiClient`. Doc comment: liên kết là điều hướng, không phải phân quyền.
2. `apps/web/lib/approvals/registry.ts`:
    - một hàm thuần `findHost(hosts, approvalType)` mà cả `approvalClient` lẫn
      `approvalInbox` gọi (một phép so tiền tố, không hai);
    - `approvalClient` thiếu `client` thì trả `apiClient()`;
    - `approvalInbox(approval)` trả `{ label, href: inbox.href(approval) }` hoặc `null`.
      `href` không bắt đầu bằng một dấu `/` (đường dẫn trong ứng dụng) thì coi là lỗi cấu
      hình: không hiện liên kết, cũng không hiện nút quyết, và hiện "This request is decided
      elsewhere." (đóng khi sai, failure-modes #7).
3. `apps/web/app/approvals/page.tsx`: approval `pending` có `approvalInbox` thì hiện nút liên
   kết (antd `Button` với `href`) mang `label`, không ô ghi chú, không "Approve", "Reject",
   kể cả với người có `approvals.decide`. Approval khác giữ nguyên hành vi. Đổi các thành
   phần shadcn của trang sang antd (CLAUDE.md, Web UI), không đổi chữ hay luồng.

## Tiêu chí chấp nhận

- [ ] Vitest `registry.test.ts` cho `findHost`, `approvalInbox` với danh sách host giả: khớp
      tiền tố thì trả liên kết; không khớp thì `null`; host không có `inbox` thì `null` và
      `approvalClient` vẫn chọn đúng client; host thiếu `client` thì `apiClient()`; `href`
      tuyệt đối (`https://…`) thì không liên kết.
- [ ] Vitest `approvals-page.test.tsx` (mock registry có một host với tiền tố `ctx.` và
      `inbox`): người có `approvals.decide` thấy approval `ctx.x` với liên kết đúng `label`,
      `href` và không có nút "Approve", "Reject" hay ô ghi chú; approval `tool.y` vẫn có hai
      nút. Gỡ nhánh `approvalInbox` trong trang thì test đỏ (ghi vào Comments).
- [ ] `HOSTS` rỗng: trang không đổi với dữ liệu hiện có (test trên).
- [ ] `rg "startsWith" apps/web/lib/approvals` ra đúng một chỗ.
- [ ] `pnpm lint`, `pnpm typecheck`, `pnpm build` xanh.

## Nguồn

- `apps/web/lib/approvals/types.ts`, `registry.ts:15-22`; `apps/web/app/approvals/page.tsx`;
  `packages/typescript/contracts/src/runs.ts:5-16`.

## Comments
