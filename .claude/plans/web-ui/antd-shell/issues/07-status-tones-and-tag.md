# 07 — Theme v3 còn lại, tông trạng thái, `StatusTag`

Status: ready-for-agent
Blocked by: 02, 05
Area: web-ui

## Mục tiêu

Theme trong `@dw/ui` mang đủ bảng token và bảng tông trạng thái của design v3, có test
tương phản giữ chúng đạt 4,5:1 ở cả sáng lẫn tối. Trên đó, một `StatusTag` dùng chung
đọc chữ, tông, biểu tượng và gợi ý từ một bảng nhãn theo mã, để mỗi context chỉ khai
bảng của mình (ví dụ bảng kết luận của sản phẩm, chữ chờ D60) mà không vẽ nhãn lần hai.

## Việc cần làm

- `packages/typescript/ui/src/theme.ts`:
    - Đối chiếu với spec mục "Token bảng màu A"; thêm phần 02 chưa có: `colorSuccessText`,
      `colorWarningText`, `colorErrorText`, `colorInfoText`, `colorBgElevated`,
      `colorTextDisabled`, `colorBorder`, nền nhạt; ở chế độ tối `colorError` `#d63a30`
      và `colorErrorText` `#ff6b61`.
    - Bo góc theo design: nút viên thuốc (component token của `Button`), trường 11px, thẻ
      20px, `Modal` và `Drawer` 24px. Cỡ nút nhỏ 28px. Không viết số trong component.
    - Một bảng `STATUS_TONES` cho sáng và tối, đúng spec mục "Tông trạng thái": `success`,
      `error`, `warning`, `gold`, `info`, `geekblue`, `unknown`, `neutral`,
      `neutralStrong`, `outline`, `infoOutline`, `successDashed`, `warningOutline`,
      `muted`; mỗi tông có `bg`, `fg`, `border`, `dashed`.
    - Phát bảng thành biến CSS (`--dw-tone-<tên>-bg|fg|border`) trên lớp theme, từ chính
      bảng đó. Đo trước xem antd v6 có phát biến cho token tự thêm không
      (`failure-modes.md` #4); không thì `ThemeProvider` phát từ cùng bảng.
- `packages/typescript/ui/src/status-tag.tsx`, xuất từ `index.ts`:
    - `type StatusLabel = { text: string; tone: StatusTone; icon?: ReactNode; tip?: string }`.
    - `type LabelTable<C extends string> = Readonly<Record<C, StatusLabel>>`.
    - `<StatusTag labels={table} code={code} size="md" | "sm" mono? />`.
    - Dựng trên antd `Tag` và `Tooltip`, theo spec mục "Nhãn":
        - cao 24px hoặc 22px, chữ 12px đậm 600, bo viên thuốc; mono thì bo 6px;
        - viền nét đứt cho `unknown`, `successDashed`, `warningOutline`; biểu tượng 11px
          trước chữ;
        - có gợi ý hoặc chữ bị cắt thì nhận focus (`tabIndex={0}`), gợi ý mở bằng rê chuột,
          focus và chạm, Esc đóng; `aria-label` là "chữ. gợi ý";
        - chữ bị cắt thì có "…" và chữ đầy đủ trong gợi ý.
    - Mã không có trong bảng (server gửi mã mới): hiện chính mã, tông `neutral`, và
      `console.error` ở bản dev. Không trả về rỗng.
- Thêm mục "Nhãn" vào fixture `/dev-login/ui-kit`: mọi tông với một bảng nhãn mẫu trung
  tính (không phải bảng của sản phẩm), cả hai cỡ, một nhãn mono, một nhãn chữ dài,
  một mã lạ.

## Tiêu chí chấp nhận

- [ ] Vitest `packages/typescript/ui/src/__tests__/contrast.test.ts` tính tỷ lệ WCAG từ
      `buildTheme` và `STATUS_TONES`, cả sáng lẫn tối:
    - chữ của mỗi tông trên nền tông đã phủ lên `colorBgContainer` và lên `colorBgLayout`
      ≥ 4,5:1;
    - `colorText`, `colorTextSecondary`, `colorTextTertiary`, `colorLink` trên hai nền đó
      ≥ 4,5:1;
    - chữ trắng trên `colorPrimary` và trên `colorError` ≥ 4,5:1;
    - `colorBorder` trên `colorBgContainer` ≥ 3:1;
    - chứng minh: đặt lại `colorError` tối là `#ff453a` thì test đỏ.
- [ ] Vitest: `StatusTag` với bảng mẫu hiện đúng chữ và biểu tượng; có gợi ý thì có
      `tabIndex=0` và `aria-label` "chữ. gợi ý"; không gợi ý và không bị cắt thì không nhận
      focus.
- [ ] Vitest: mã lạ hiện chính mã; đổi nhánh dự phòng thành trả `null` thì test đỏ.
- [ ] tsc: một bảng thiếu mã của union bị báo lỗi kiểu (một dòng `// @ts-expect-error`
      trong tệp test, chạy qua `pnpm run typecheck`).
- [ ] Playwright `@ui` trên fixture: Tab tới nhãn có gợi ý thì gợi ý hiện, Esc thì đóng;
      ở `phone-390` chạm vào nhãn thì gợi ý bật, chạm lần nữa thì tắt.
- [ ] Playwright: nút chính trên fixture có `border-radius` không nhỏ hơn nửa chiều cao;
      ô nhập 11px; ở chế độ tối nút nguy hiểm có nền `rgb(214, 58, 48)`.
- [ ] Không có màu hex, `rgba(` hay số px của bo góc trong `status-tag.tsx`.
- [ ] `pnpm --filter @dw/ui test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Token bảng màu A", "Tông trạng thái", "Nhãn" (chép từ design v3
  `EHSDT v3.dc.html` biến CSS, `v3-kit.js` `TONES` và `L`, `V3Tag.dc.html`,
  `V3Catalog.dc.html`).
- D07 (Đạt 2/10/2026): theo design v3, chỉ được đậm màu chữ chưa đạt 4,5:1.
- `CLAUDE.md` "Web UI": `@dw/ui` giữ theme và nhãn trạng thái; không bọc lại antd.
- `ui-quality.md` §1, §7 (màu không bao giờ là tín hiệu duy nhất; tím chỉ cho chưa
  rõ), §12 (tương phản; bẫy: màu trạng thái trên nền nhạt của chính nó, tag preset của
  antd) (nhánh `bidding`).
- Spec, Câu hỏi còn mở 7 (catalog và CSS khung lệch màu lỗi).
- Ticket 02, mục Comments.

## Comments

- **2/10/2026, ticket 02 sau review.** 02 đã lấy trước, đúng giá trị của spec:
  `colorSuccessText`, `colorWarningText`, `colorErrorText` ở cả hai chế độ, và
  `colorError` tối `#d63a30` (chữ lỗi tối `#ff6b61`). Badge và Alert nguy hiểm của
  `@dw/ui` đọc chữ từ ba token đó (`text-success-text`, `text-warning-text`,
  `text-destructive-text`). `theme.ts` có thêm một thuật toán chạy sau
  `darkAlgorithm` để giữ năm seed (`colorPrimary`, `colorLink`, `colorSuccess`,
  `colorWarning`, `colorError`): không có nó, antd tính lại chúng ở chế độ tối và
  `#0071e3` thành `#0363c4`. Test tương phản của 07 nên đọc token từ
  `theme.getDesignToken(buildTheme(...))`, không từ bảng màu, vì chỉ giá trị antd tính
  ra mới là giá trị hiển thị. Phần còn lại vẫn của 07.
