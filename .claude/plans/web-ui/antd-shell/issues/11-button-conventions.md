# 11 — Quy ước nút

Status: ready-for-agent
Blocked by: 05, 07
Area: web-ui

## Mục tiêu

Mọi màn dùng nút antd theo cùng sáu kiểu của design, và hai quy ước truy cập có chốt:
nút bị khóa nói lý do bằng chữ cạnh nút, nút chỉ có biểu tượng có tên đọc được.
`@dw/ui` không bọc lại `Button` (`CLAUDE.md` "Web UI"), nên ticket này là quy ước, mục
trên fixture và test, không phải một component mới.

Hôm nay quy ước chỉ nằm trong spec (mục "Nút (V3Btn) và trường (V3Field)"); 07 chỉ đặt
bo góc và cỡ nút.

## Việc cần làm

- Ghi quy ước trong chú thích đầu `packages/typescript/ui/src/theme.ts`, cạnh token của
  `Button`, đúng spec:
    - chính → `type="primary"`; mặc định → `type="default"`; nền xám →
      `color="default" variant="filled"`; liên kết → `type="link"`; nguy hiểm →
      `type="primary" danger`; nguy hiểm viền → `danger`;
    - đang chạy là `loading`: chặn bấm lần hai, `aria-busy`;
    - nút khóa: `disabled`, lý do trong `Tooltip`, và cùng câu đó bằng chữ cạnh nút,
      nối bằng `aria-describedby`. Nút khóa không nhận focus và chạm vào không hiện
      gì, nên Tooltip một mình không đủ;
    - nút chỉ có biểu tượng: `aria-label`.
- Đo `Button` của antd 6.6.5 trước (`failure-modes.md` #4): `loading` có đặt
  `aria-busy` không, có chặn `onClick` không; `disabled` có giữ được focus và
  `aria-describedby` không. Phần antd không làm thì ghi dưới Comments và chọn cách bù
  trong `@dw/ui` (ví dụ một hàm trả props), không bọc lại `Button`.
- Luật ESLint trong `apps/web/.eslintrc.json` (`no-restricted-syntax`): phần tử
  `Button` có thuộc tính `icon`, không có con và không có `aria-label` thì lỗi. Đo xem
  bộ chọn esquery viết được không; không được thì ghi lý do dưới Comments và để test
  Playwright dưới đây là chốt.
- Thêm mục "Nút" vào fixture `/dev-login/ui-kit`: sáu kiểu ở ba cỡ, một nút `loading`,
  một nút khóa có dòng lý do, một nút chỉ có biểu tượng.

## Tiêu chí chấp nhận

- [ ] Một test chạy ESLint (`ESLint#lintText`) trên `<Button icon={<X />} />` ra lỗi
      đúng luật; `<Button icon={<X />} aria-label="Đóng" />` và `<Button>Lưu</Button>`
      không ra lỗi.
- [ ] Playwright `@ui` trên fixture: mọi `button` có tên đọc được
      (`getByRole("button")` không có tên rỗng); xóa `aria-label` của nút chỉ có biểu
      tượng trên fixture thì test đỏ.
- [ ] Playwright `@ui`: nút khóa có `aria-describedby` trỏ vào một phần tử đang hiện
      (không phải Tooltip) chứa lý do.
- [ ] Playwright `@ui`: bấm nút `loading` không gọi hành động lần hai; nút có
      `aria-busy="true"` (hoặc Comments ghi antd làm khác và đã bù thế nào).
- [ ] Ở `phone-320` mục "Nút" không cuộn ngang; vùng chạm mỗi nút ít nhất 24×24.
- [ ] `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Nút (V3Btn) và trường (V3Field)" (chép từ design v3 `V3Btn.dc.html`).
- `CLAUDE.md` "Web UI": một hệ component, context dùng antd trực tiếp, `@dw/ui` không
  bọc lại.
- `ui-quality.md` §3 (antd đã bỏ lượt bấm khi `loading`), §5 (lý do khóa trong
  Tooltip và bằng chữ cạnh nút), §12 (tên đọc được, vùng chạm) (nhánh `bidding`).
- `failure-modes.md` #3, #4.

## Comments
