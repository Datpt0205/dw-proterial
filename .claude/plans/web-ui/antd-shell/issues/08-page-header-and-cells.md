# 08 — `PageHeader`, `MaskedValue`, `AbsentValue`

Status: ready-for-agent
Blocked by: 05, 07
Area: web-ui

## Mục tiêu

Ba phần dùng chung mà màn nào cũng cần, trong `@dw/ui`:

- đầu trang giống nhau ở mọi màn;
- ô "Đã ẩn" cho giá trị API không trả vì vai người xem, và "••••" cho trường hạn chế
  bị che;
- ô "Chưa rõ", "Không áp dụng", "—" để bốn nghĩa của một ô trống không lẫn nhau.

`MaskedValue` không nhận giá trị, nên không có đường nào đưa số bị ẩn vào DOM.

## Việc cần làm

- `packages/typescript/ui/src/page-header.tsx`, theo đầu trang của design v3:
    - `breadcrumb`: mục `{ label, href?, mono? }`, trong `<nav aria-label="Vị trí">`,
      ngăn bằng "›", chữ 12px màu chữ mờ, mã định danh chữ mono. Liên kết do app truyền
      vào (không import Next).
    - `tags`: hàng nhãn trên tiêu đề, thường là `StatusTag`.
    - `title`: một `<h1>`, 24px ở trang danh sách, 22px ở trang một hồ sơ
      (`variant: "list" | "record"`). Cỡ chữ lấy từ token tiêu đề của theme, không viết
      px trong component.
    - `subtitle`: 13px, chữ phụ.
    - `actions`: bên phải từ 992px, xuống dưới tiêu đề khi hẹp; lý do của nút khóa do màn
      đặt cạnh nút.
    - Chú thích ở `apps/web/components/page-heading.tsx`: trang nào sửa lần sau thì chuyển
      sang `PageHeader`; không quét một lượt.
- `packages/typescript/ui/src/masked-value.tsx`:
    - `kind: "hidden"` → `LockOutlined` + "Đã ẩn", chữ phụ; `kind: "restricted"` →
      `EyeInvisibleOutlined` + "••••".
    - `aria-label`: mặc định "Giá trị bị ẩn với vai của bạn" và "Trường bị che"; màn có
      thể truyền câu riêng.
    - `reason?`: câu ai được xem, hiện trong gợi ý (rê chuột, focus, chạm); không chọn
      chép được (`user-select: none`).
    - `mode: "cell" | "region"`: `region` là khối `role="note"` cao tối thiểu 56px, hiện
      câu `reason` một lần cho cả vùng.
    - `loading`: thanh khung xương rộng cố định 80px.
    - Không có prop `value` hay `children`.
- `packages/typescript/ui/src/absent-value.tsx`:
    - `kind: "unknown"` → `QuestionCircleOutlined` + "Chưa rõ", tông `unknown` viền nét
      đứt; chữ thay được (ví dụ "chưa rõ giờ").
    - `kind: "not_applicable"` → `MinusOutlined` + "Không áp dụng", tông `neutral`;
      `reason` bắt buộc, hiện trong gợi ý.
    - `kind: "none"` → "—", chữ mờ, `aria-label` "Không có giá trị".
- Thêm mục "Đầu trang" và "Ô đặc biệt" vào fixture `/dev-login/ui-kit`: hai kiểu đầu
  trang (một có breadcrumb dài và tiêu đề 160 ký tự), năm loại ô, ô khóa đang tải, một
  vùng khóa.

## Tiêu chí chấp nhận

- [ ] tsc: `<MaskedValue kind="hidden" value={1285000} />` là lỗi kiểu (dòng
      `// @ts-expect-error` trong tệp test, chạy qua `pnpm run typecheck`). Thêm prop
      `value` vào component thì dòng đó thành lỗi "unused directive" và typecheck đỏ.
- [ ] Vitest: DOM của `MaskedValue` (mọi `kind`, `mode`, cả `loading`) không có chữ số
      nào; thanh đang tải rộng 80px bất kể ngữ cảnh.
- [ ] Vitest: `AbsentValue kind="unknown"` không bao giờ in "—"; `kind="none"` chỉ in
      "—"; thiếu `reason` ở `not_applicable` là lỗi kiểu.
- [ ] Vitest: `PageHeader` có đúng một `h1`; breadcrumb là `nav` tên "Vị trí"; mục
      `mono` dùng phông mono.
- [ ] Playwright `@ui` trên fixture: ở `phone-320` tiêu đề 160 ký tự xuống dòng, không
      cuộn ngang, nút hành động xuống dưới tiêu đề; Tab tới ô "Đã ẩn" thì gợi ý hiện; chọn
      bằng chuột kéo qua ô thì `window.getSelection()` không chứa "Đã ẩn".
- [ ] Không có màu hex, `rgba(` hay số px của chữ trong ba tệp mới.
- [ ] `pnpm --filter @dw/ui test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Ô đặc biệt" (chép từ design v3 `V3Price.dc.html` và bảng ô đặc biệt của
  `V3Catalog.dc.html`); đầu trang chép từ `V3Bid.dc.html`, `V3Bids.dc.html`,
  `V3Admin.dc.html`.
- `CLAUDE.md` "Web UI": `@dw/ui` giữ đầu trang và các phần trung tính một context dùng
  lại.
- `ui-quality.md` §6 (API bỏ giá trị ra; ô khóa ghi "Đã ẩn", không "0", không "—"; một
  thành phần che dùng chung), §8 (chưa rõ khác không có) (nhánh `bidding`).
- Design v3 `README.md`: "server lọc số khỏi API, ẩn ô không phải phân quyền". Prototype
  `V3Price` nhận `value` và `canSee`; bản code bỏ cả hai.
- Spec, Câu hỏi còn mở 5 (API báo "bị ẩn" thế nào).

## Comments
