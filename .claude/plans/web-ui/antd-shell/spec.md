# S0 — Shell antd dùng chung

Area: web-ui · Nhánh: `main` (worktree `codebase-main`) · Viết: 2/10/2026

Lát nền tảng, trung tính với sản phẩm. Sản phẩm đầu tiên dựng trên nền tảng (bản
demo) sẽ dùng mọi thứ ở đây, nhưng không chữ, không bảng nhãn, không vai nào của nó
nằm trong lát này. Bản thiết kế v3 chỉ có trên máy Đạt, nên mọi hành vi cần dùng được
chép vào spec này; ticket dẫn về mục ở đây, không dẫn về tệp thiết kế.

Dẫn chứng ngoài repo này, để một dự án khác dựng trên nền tảng đọc đúng: tên tệp
`*.dc.html` (`EHSDT v3.dc.html`, `V3Catalog.dc.html`…) là tệp của bản bàn giao design
v3 mà sản phẩm đầu tiên dùng, không nằm ở đây; "nhánh `bidding`" là repo của sản phẩm
đó (`ui-quality.md`, ADR của context). Mọi hành vi lát này cần đã chép vào spec; một
dự án khác thay bản vẽ của mình mà không phải đọc các tệp đó.

## Mục tiêu

Trước khi có màn nghiệp vụ nào, web có một khung dùng chung đúng như design v3 và
`CLAUDE.md` "Web UI". Khi lát xong, một người mở bản demo thấy:

- khung menu ngang 56px, dưới 992px thành ngăn kéo; bảng màu A, sáng hoặc tối theo máy;
- mọi thời điểm in "09:00 14/10/2026 (giờ Việt Nam)", kể cả trên máy đặt múi giờ khác;
  hạn chỉ có ngày không lùi một ngày; "chưa rõ" khác "không có";
- tiền in "18.450.000.000 đ", không bao giờ "₫";
- thông báo nổi qua `App.useApp()`, câu của server, không lộ mã máy;
- nhãn trạng thái đọc từ một bảng nhãn theo mã, đủ tương phản ở cả hai chế độ;
- ô "Đã ẩn" khi API không trả giá trị, và các ô "Chưa rõ", "Không áp dụng", "—";
- trạng thái vùng đúng theo mã lỗi: 403, 404, xung đột, lỗi máy chủ, mất mạng;
- trang đứng vững ở 320px và ở cả hai phía 992px.

## Trong phạm vi

- Shell antd: theme A sáng/tối trong `@dw/ui`, provider `vi_VN` phát CSS variable,
  `AppShell` menu ngang, thứ tự layer, Tailwind ánh xạ vào token antd (ticket 02).
- `apps/web/lib/dates.ts` và `apps/web/lib/money.ts` (03, 04).
- Hạ tầng kiểm thử UI: project Playwright theo bề rộng và theo múi giờ, trang fixture
  không cần API, vitest cho `@dw/ui` (05).
- Thông báo qua `App.useApp()`, gỡ sonner (06).
- Phần còn lại của theme v3: tông trạng thái, token chữ theo trạng thái, bo góc, test
  tương phản; `StatusTag` theo bảng nhãn (07).
- `PageHeader`, `MaskedValue`, `AbsentValue` trong `@dw/ui` (08).
- `RegionState` ánh xạ mã lỗi sang trạng thái; phát hiện mất mạng một lần trong shell
  (09).
- CI chạy test web, cả spec fixture lẫn spec cần API (10, chờ Đạt).
- Quy ước nút (11) và trường (12) của design: theme, mục trên fixture, test.
- Nút "Bỏ qua tới nội dung chính" và vùng `main` (13); cảnh báo phiên sắp hết hạn
  2 phút trước (14). Hai việc này là yêu cầu truy cập (WCAG 2.4.1, 2.2.1), nên không
  để P1.
- Chế độ tối không nháy sáng khi tải (15); mục menu hiện tại đậm 600, màu chữ chính
  (07).
- `<html lang="vi">` và nhãn menu nền tảng bằng tiếng Việt (18, chờ Đạt, Câu hỏi còn
  mở 4).

## Ngoài phạm vi

- Bảng nhãn của sản phẩm (kết luận, mức độ, trạng thái gói, trạng thái cổng): do
  context của sản phẩm khai, chữ chờ D60.
- Đọc số tiền thành chữ: thuộc domain của context của sản phẩm (D12). `lib/money.ts` chỉ định dạng và đọc số.
- Mục menu của sản phẩm: context khai trong manifest của nó, nối một lần ở
  `lib/nav/registry.ts`.
- Thay các trang shadcn hiện có: thay khi trang đó được sửa lần sau, không quét một
  lượt (`CLAUDE.md`).
- Dịch các trang nền tảng đang viết tiếng Anh (Câu hỏi còn mở 4).
- Màn Duyệt theo design v3 (`V3Approvals`): thuộc lát sản phẩm làm cổng.
- **P1, đã có ticket, không chặn slice:** nút chọn Sáng / Tối / Theo máy trong menu
  người dùng (16, chờ Câu hỏi còn mở 6); bảng lệnh Ctrl K (17).
- **P1, thành ticket sau khi cần:** chỉ báo "Đang lưu… / Đã lưu"; băng quyền hỗ trợ;
  script chụp prototype cạnh app; `Idempotency-Key` trong API client (cần trước màn
  đầu tiên có nút quyết cổng).
- **P2:** chuyển động riêng của design (vào trang lệch nhịp, nháy dòng 2,4s, đường cong
  nảy). Code dùng token `motion*` của antd.

## Vai và quyền

Lát này không biết vai nào. Sản phẩm có vai riêng, do server phân giải; S0 không thêm,
không đọc vai nào.

- Shell nhận danh sách mục menu đã lọc theo scope (cơ chế sẵn có ở
  `components/app-frame.tsx`). Ẩn mục menu không phải là phân quyền.
- `MaskedValue` hiện khi API không trả trường. Nó không nhận giá trị, nên không có
  đường nào đưa số bị ẩn vào DOM. Trình duyệt không tự quyết ai được xem.
- `RegionState` hiện đúng điều server nói: `permission_denied` thành 403,
  `not_found` thành 404. Việc trả 404 cho tenant khác là của server.

## Màn hình

| Route                    | File v3                          | Hiện gì                                                                                                                                                                               |
| ------------------------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mọi trang đã đăng nhập   | `EHSDT v3.dc.html` (khung)       | `AppShell`: header 56px, menu ngang từ 992px, ngăn kéo dưới 992px; sáng/tối theo máy; băng mất mạng dưới header (09); thông báo nổi giữa đáy (06)                                     |
| `/dev-login/layer-check` | không                            | Fixture của 02: shell và một nút antd mang lớp Tailwind. Chỉ có ở bản dev-auth, bản khác trả 404                                                                                      |
| `/dev-login/ui-kit`      | `V3Catalog.dc.html` (`#catalog`) | Fixture của 05 (giờ); các ticket 04, 06–09, 11, 12, 17 thêm phần: tiền, thông báo, nhãn, ô đặc biệt, trạng thái vùng, nút, trường, bảng lệnh. Chỉ có ở bản dev-auth, bản khác trả 404 |

Hai fixture là bản code của trang `#catalog`: cho Playwright chạy ở mọi bề rộng và múi
giờ mà không cần API, và cho người xem từng trạng thái cạnh nhau.

### Khung (EHSDT v3.dc.html)

- **Header** dính trên cùng, cao 56px, nền kính mờ (nền thẻ 78% + blur 20px), kẻ 1px
  dưới. Trái sang phải: nút "Mở menu" 44×44 (chỉ dưới 992px) · thương hiệu (biểu tượng
  26px bo 7px nền màu chính, tên 15px đậm 600; tên ẩn ở 992–1099px) · vạch ngăn ·
  workspace · menu ngang · khoảng trống · các nút bên phải (chuông 36×36, avatar 32px).
- **Menu ngang** chữ 14px; mục hiện tại đậm 600, màu chữ chính, `aria-current="page"`.
  Số đếm cạnh mục là viên 18px: 0 thì ẩn, quá 99 in "99+". Hết chỗ thì dồn vào "…"
  (antd tự làm).
- **Ngăn kéo** từ trái, rộng 280px, có lớp phủ; mục cao 44px chữ 15px; nút "Đóng menu"
  44×44; Esc hoặc bấm lớp phủ thì đóng; đổi trang thì đóng.
- **Nội dung** `<main id="main" tabIndex={-1}>`, đệm 24px 28px 80px từ 992px, 16px 14px
  80px dưới 992px.
- **Băng mất mạng** dính ngay dưới header, rộng hết trang, `role="status"`, nền và chữ
  tông cảnh báo: "Mất kết nối lúc 14:05 30/09/2026 (giờ Việt Nam). Chưa có gì được gửi
  đi; dữ liệu bạn đã nhập vẫn giữ." (09).
- **Thông báo nổi** giữa đáy, tối đa 3 cái, cái mới đẩy cái cũ. Thành công và thông tin
  tự tắt sau 4,2 giây; có nút Hoàn tác thì 7 giây, và chỉ khi server hoàn tác thật; lỗi
  có nút "Thử lại" không tự tắt (06).
- **Hộp xác nhận** focus mặc định vào "Hủy"; hộp gõ mã focus vào ô gõ.
- **Bỏ qua tới nội dung chính:** liên kết đầu tiên của trang, ẩn tới khi nhận focus
  bằng Tab, hiện ở góc trên trái. Enter chuyển focus vào `main#main` (13).
- **Cảnh báo phiên:** 2 phút trước khi phiên đăng nhập hết, một hộp thoại báo giờ hết
  phiên và có nút chính "Ở lại đăng nhập", focus vào nút đó. Bấm thì gia hạn phiên tại
  chỗ; trang và dữ liệu đã nhập giữ nguyên. Không gia hạn được thì hộp đổi sang nút
  "Đăng nhập lại" (đề xuất). Design thêm mục này theo WCAG 2.2.1 (14).
- **Bảng lệnh** Ctrl K (Cmd K trên Mac): ô tìm và danh sách mục menu người đó thấy;
  Enter mở mục, Esc đóng (17, P1). Chỉ liệt kê mục menu là phần đề xuất của spec này.
- **Menu người dùng** có ô Sáng / Tối / Theo máy, mặc định Theo máy (16, P1, chờ Câu
  hỏi còn mở 6).

### Token bảng màu A (EHSDT v3.dc.html, V3Catalog)

D07: theo design v3 hoàn toàn; chỉ được đậm màu chữ chưa đạt 4,5:1. Tên token antd ở
cột đầu; giá trị lấy từ CSS của khung v3, không lấy bảng catalog khi hai bên lệch
(xem Câu hỏi còn mở 7).

| Token antd                        | Sáng                           | Tối                           | Dùng cho                     |
| --------------------------------- | ------------------------------ | ----------------------------- | ---------------------------- |
| `colorPrimary`                    | `#0071e3`                      | `#0071e3`                     | nút chính, focus             |
| `colorLink`, `colorInfoText`      | `#0060c0`                      | `#4da3ff`                     | liên kết, chữ tông thông tin |
| `colorSuccess`                    | `#1f9d4c`                      | `#30d158`                     | biểu tượng, viền             |
| `colorSuccessText`                | `#146c33`                      | `#30d158`                     | chữ tông thành công          |
| `colorWarning`                    | `#c26a00`                      | `#ff9f0a`                     | biểu tượng, viền             |
| `colorWarningText`                | `#9a5200`                      | `#ff9f0a`                     | chữ tông cảnh báo            |
| `colorError`                      | `#c4271e`                      | `#d63a30`                     | nền nút nguy hiểm, viền      |
| `colorErrorText`                  | `#c4271e`                      | `#ff6b61`                     | chữ tông lỗi                 |
| `colorText`                       | `#1d1d1f`                      | `#f5f5f7`                     | chữ chính                    |
| `colorTextSecondary`              | `#515154`                      | `#c7c7cc`                     | chữ phụ, "Đã ẩn"             |
| `colorTextTertiary`               | `#6e6e73`                      | `#8e8e93`                     | nhãn bảng, ghi chú           |
| `colorTextDisabled`               | `#86868b`                      | `#8e8e93`                     | chỉ cho điều khiển bị khóa   |
| `colorBorder`                     | `#8e8e93`                      | `#8e8e93`                     | viền trường                  |
| `colorBorderSecondary`            | `#e3e3e8`                      | `#3a3a3c`                     | đường kẻ                     |
| `colorBgLayout`                   | `#f5f5f7`                      | `#000000`                     | nền trang                    |
| `colorBgContainer`                | `#ffffff`                      | `#1c1c1e`                     | thẻ, bảng                    |
| `colorBgElevated`                 | `#ffffff`                      | `#232326`                     | hộp thoại, menu thả          |
| `colorFill`, `colorFillSecondary` | `rgba(120,120,128,.16)`, `.08` | `rgba(120,120,128,.3)`, `.18` | nền nhạt                     |

Bo góc: nút viên thuốc (999px), trường 11px, thẻ 20px, hộp thoại và Drawer 24px. Cỡ
nút: nhỏ 28px, vừa 32px, lớn 40px. Chữ: 14px, dòng 1,5; họ chữ `-apple-system,
BlinkMacSystemFont, 'SF Pro Text', 'Be Vietnam Pro', system-ui, sans-serif`; chữ mono
`'JetBrains Mono', ui-monospace, monospace`. Không chữ nào dưới 12px.

### Tông trạng thái (v3-kit.js `TONES`)

Mỗi màu mang một nghĩa. Nền là màu có alpha phủ lên nền thẻ hoặc nền trang. Tỷ lệ
tương phản đo 2/10/2026 trên giá trị dưới đây, chữ trên nền đã phủ: mọi cặp đạt
4,5:1 ở cả hai chế độ (thấp nhất: `error` tối trên nền thẻ, 4,81). Cột "Đo sáng" ghi
số của chế độ sáng, trên nền thẻ / nền trang.

| Tông (tên code)  | Sáng: nền · chữ · viền                                 | Tối: nền · chữ · viền                                  | Đo sáng     | Nghĩa                          |
| ---------------- | ------------------------------------------------------ | ------------------------------------------------------ | ----------- | ------------------------------ |
| `success`        | `rgba(52,199,89,.14)` · `#146c33` · —                  | `rgba(48,209,88,.18)` · `#30d158` · —                  | 5,81 / 5,39 | đã thỏa, đã xác minh, đã duyệt |
| `error`          | `rgba(255,59,48,.10)` · `#c4271e` · —                  | `rgba(255,69,58,.2)` · `#ff6b61` · —                   | 5,03 / 4,64 | chặn cứng, lỗi                 |
| `warning`        | `rgba(255,159,10,.16)` · `#9a5200` · —                 | `rgba(255,159,10,.18)` · `#ff9f0a` · —                 | 5,21 / 4,84 | chặn mềm, chờ, sắp hết         |
| `gold`           | `rgba(255,204,0,.2)` · `#855c00` · —                   | `rgba(255,214,10,.16)` · `#ffd60a` · —                 | 5,43 / 5,06 | có rủi ro, số liệu cũ          |
| `info`           | `rgba(0,113,227,.10)` · `#0060c0` · —                  | `rgba(10,132,255,.2)` · `#4da3ff` · —                  | 5,33 / 4,92 | đang xử lý, chờ duyệt          |
| `geekblue`       | `rgba(47,84,235,.10)` · `#1d39c4` · —                  | `rgba(89,126,247,.2)` · `#85a5ff` · —                  | 7,45 / 6,87 | đã gửi, chờ kết quả            |
| `unknown`        | `rgba(175,82,222,.10)` · `#7b36b3` · `#7b36b3` nét đứt | `rgba(191,90,242,.18)` · `#d18cf7` · `#d18cf7` nét đứt | 6,14 / 5,67 | chưa rõ; chỉ nghĩa này         |
| `neutral`        | `rgba(120,120,128,.16)` · `#515154` · —                | `rgba(120,120,128,.3)` · `#c7c7cc` · —                 | 6,54 / 6,06 | trung tính                     |
| `neutralStrong`  | như `neutral`, chữ `#1d1d1f`                           | như `neutral`, chữ `#f5f5f7`                           | 13,9 / 12,9 | đóng, đã nộp                   |
| `outline`        | trong suốt · `#515154` · `#8e8e93`                     | trong suốt · `#c7c7cc` · `#8e8e93`                     | 7,91 / 7,26 | nhãn phụ                       |
| `infoOutline`    | trong suốt · `#0060c0` · `#0071e3`                     | trong suốt · `#4da3ff` · `#0071e3`                     | 6,11 / 5,62 | mới, chưa bắt đầu              |
| `successDashed`  | trong suốt · `#146c33` · `#1f9d4c` nét đứt             | trong suốt · `#30d158` · `#30d158` nét đứt             | —           | đạt có điều kiện               |
| `warningOutline` | trong suốt · `#9a5200` · `#c26a00` nét đứt             | trong suốt · `#ff9f0a` · `#ff9f0a` nét đứt             | —           | cần xem                        |
| `muted`          | trong suốt · `#6e6e73` · `rgba(60,60,67,.2)`           | trong suốt · `#8e8e93` · `rgba(120,120,128,.45)`       | 5,07 / 4,66 | không áp lúc này               |

Tím chỉ dùng cho "chưa rõ". Màu không bao giờ là tín hiệu duy nhất: nhãn nào cũng có
chữ, tông nào mang nghĩa cũng có biểu tượng.

### Nút (V3Btn) và trường (V3Field)

`@dw/ui` không bọc lại antd (`CLAUDE.md`), nên S0 không có `V3Btn` hay `V3Field`.
Design đưa vào theme và quy ước:

- Sáu kiểu nút: chính → `type="primary"`; mặc định → `type="default"`; nền xám →
  `variant="filled"`; liên kết → `type="link"`; nguy hiểm → `type="primary" danger`;
  nguy hiểm viền → `danger`. Đang chạy là `loading` (chặn bấm, `aria-busy`). Nút khóa
  có lý do bằng chữ cạnh nút, không chỉ trong Tooltip. Nút chỉ có biểu tượng có
  `aria-label`.
- Trường: nhãn 13px đậm 500 trên ô, dấu `*` màu lỗi cho trường bắt buộc; gợi ý và lỗi
  12px dưới ô, lỗi có biểu tượng; bộ đếm "Còn N ký tự" khi đã dùng 90%, "Vượt N ký tự"
  màu lỗi. Ô tiền căn phải, chữ số đều, hậu tố "đ", dùng `lib/money.ts`. Ô giờ có hậu
  tố "giờ Việt Nam", ô ngày `DD/MM/YYYY`, dùng `lib/dates.ts`.

### Nhãn (V3Tag)

- Đọc chữ, tông, biểu tượng và gợi ý từ một bảng nhãn theo mã. Mã không có trong bảng
  thì hiện chính mã, tông trung tính.
- Cao 24px (cỡ vừa) hoặc 22px (cỡ nhỏ); chữ 12px đậm 600; bo viên thuốc. Kiểu mono:
  chữ mono đậm 500, bo 6px. Biểu tượng 11px trước chữ.
- Có gợi ý hoặc chữ bị cắt thì nhãn nhận focus bằng Tab; gợi ý hiện khi rê chuột, khi
  focus, và bật tắt khi chạm. `aria-label` là "chữ. gợi ý".
- Chữ dài thì cắt bằng dấu "…", chữ đầy đủ trong gợi ý.

### Trạng thái vùng (V3State)

| Kiểu          | Biểu tượng (antd)       | Tông      | Tiêu đề mặc định              | Mô tả mặc định                                                             |
| ------------- | ----------------------- | --------- | ----------------------------- | -------------------------------------------------------------------------- |
| `loading`     | khung xương 6 dòng 56px | —         | (`aria-label` "Đang tải")     | —                                                                          |
| `empty`       | `InboxOutlined`         | `info`    | Chưa có dữ liệu               | (màn truyền câu hướng dẫn và nút đầu tiên)                                 |
| `nomatch`     | `FilterOutlined`        | `neutral` | Không có mục khớp bộ lọc      | (nút "Xóa bộ lọc")                                                         |
| `search`      | `SearchOutlined`        | `neutral` | Không có kết quả              | —                                                                          |
| `partial`     | `EllipsisOutlined`      | `neutral` | Danh sách chưa tải hết        | Tìm trong trình duyệt chỉ phủ các dòng đã tải.                             |
| `error`       | `DisconnectOutlined`    | `error`   | Không tải được dữ liệu        | câu của server; "Mã yêu cầu: {request_id}" chữ mono; nút "Thử lại"         |
| `forbidden`   | `LockOutlined`          | `neutral` | Bạn không có quyền mở mục này | câu của server                                                             |
| `notfound`    | `CompassOutlined`       | `neutral` | Không tìm thấy                | Không có mục này, hoặc liên kết đã cũ.                                     |
| `conflict`    | `SwapOutlined`          | `warning` | Có người vừa sửa mục này      | câu của server; nút "Tải lại"; màn giữ những gì người dùng đã gõ (đề xuất) |
| `entitlement` | `CrownOutlined`         | `neutral` | Gói dịch vụ chưa gồm mục này  | câu của server; không phải 403 (đề xuất)                                   |
| `session`     | `LoginOutlined`         | `neutral` | Cần đăng nhập lại             | nút "Đăng nhập lại" (đề xuất)                                              |
| `offline`     | `DisconnectOutlined`    | `warning` | Mất kết nối                   | Dữ liệu đã tải vẫn xem được. Thao tác ghi mở lại khi có mạng.              |
| `stale`       | `HistoryOutlined`       | `gold`    | Số liệu cũ                    | (màn truyền thời điểm cập nhật)                                            |

`error` có `role="alert"`, các kiểu khác `role="status"`. Hai cỡ: đầy đủ (thẻ, đệm
40px 32px, tiêu đề 18px) và gọn (trong vùng, đệm 20px 4px, tiêu đề 15px). Dòng "(đề
xuất)" là chữ của spec này, design không vẽ.

### Ô đặc biệt (V3Price, `#catalog`)

| Ô             | Hiện                                                               | Khi nào                                                                                  |
| ------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Đã ẩn         | `LockOutlined` + "Đã ẩn", chữ phụ                                  | API không trả giá trị vì vai người xem. Không chấm, không độ dài, không chọn chép được   |
| ••••          | `EyeInvisibleOutlined` + "••••"                                    | trường hạn chế bị che (ví dụ dưới quyền hỗ trợ)                                          |
| Chưa rõ       | `QuestionCircleOutlined` + "Chưa rõ", tông `unknown` viền nét đứt  | thiếu dữ kiện, máy không đọc được                                                        |
| Không áp dụng | `MinusOutlined` + "Không áp dụng", tông `neutral`, gợi ý ghi lý do | không áp cho mục này                                                                     |
| —             | "—", chữ mờ                                                        | trường không bắt buộc người dùng chưa nhập. Không bao giờ thay cho "Chưa rõ" hay "Đã ẩn" |

Câu ai được xem (ví dụ "Chỉ vai X và Y xem được") hiện một
lần ở vùng, không lặp ở từng ô; ở ô chỉ có trong gợi ý. Khi đang tải: thanh khung
xương rộng cố định 80px, không lộ độ dài số.

### Giờ (v3-kit.js `T`)

Mọi thời điểm tính theo `Asia/Ho_Chi_Minh`, đồng hồ 24 giờ, luôn có năm.

| Dạng                           | Ví dụ                                                                                                                                |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Đầy đủ                         | `09:00 14/10/2026 (giờ Việt Nam)`                                                                                                    |
| Trong ô bảng                   | `09:00 14/10/2026`; tiêu đề cột ghi "(giờ Việt Nam)"                                                                                 |
| Chỉ có ngày                    | `14/10/2026`                                                                                                                         |
| Có ngày, thiếu giờ             | `14/10/2026 · chưa rõ giờ` (tông `unknown`)                                                                                          |
| Hết ngày                       | `hết ngày 25/02/2027 (giờ Việt Nam)`                                                                                                 |
| Tương đối (thông báo, nhật ký) | `3 phút trước · 14:07 30/09/2026 (giờ Việt Nam)`; "vừa xong"; "N giờ trước" cùng ngày; "Hôm qua" theo lịch Việt Nam; xa hơn thì ngày |

Tránh: `14/10 9h`, giờ theo múi của máy người xem, ngày trước giờ.

### Tiền (v3-kit.js `money`)

`18.450.000.000 đ`: dấu chấm ngăn nghìn, khoảng trắng, "đ". Số trong bảng căn phải,
chữ số đều. Dạng rút gọn `18,45 tỷ` chỉ ở chỗ màn vẽ rút gọn, luôn kèm số đầy đủ khi rê
chuột, chạm hoặc focus.

## Dữ liệu

Không có bảng, cột, RLS hay migration mới. Lát chỉ đọc hợp đồng sẵn có:

- `ErrorResponse` (`code`, `message`, `details`, `request_id`) và `ErrorCode` trong
  `packages/typescript/contracts/src/error.ts`, bản sao của
  `dw_kernel.errors.ErrorCode`. `RegionState` lấy danh sách mã từ đó, không chép lại.
- `ApiError` trong `packages/typescript/api-client/src/client.ts`: `message` là
  `"<code>: <câu>"`, chỉ dành cho log; câu cho người đọc là `body.message`
  (`errorMessage()` trong `apps/web/lib/error-message.ts`).
- `platform.tenants.timezone` có cột và có ô sửa ở Quản trị › Cài đặt tenant nhưng
  không chỗ nào đọc. S0 không đọc nó (Câu hỏi còn mở 2).

## API và luồng

Không có endpoint, worker, graph hay điểm interrupt mới. Ba luồng phía trình duyệt:

1. **Lỗi thành trạng thái.** Lệnh gọi API thất bại → `apps/web/lib/error-message.ts`
   chuẩn hóa thành `{ code, message, requestId }` hoặc "mất mạng" → `RegionState` tra
   một bảng `ErrorCode → kiểu` trong `@dw/ui` → vẽ kiểu tương ứng.
2. **Mất mạng.** `@dw/ui` nghe `online`/`offline` một lần, giữ `{ online, since }`
   trong context; shell vẽ băng; màn đọc `online` để khóa thao tác ghi.
3. **Thông báo.** Màn và hook gọi `App.useApp()` (`notification`, `message`,
   `modal`); cấu hình mặc định (vị trí đáy, tối đa 3) đặt một lần trên `<App>` trong
   `ThemeProvider`.

## Quy tắc và kiểm soát

`.claude/rules/ui-quality.md` hiện chỉ có trên nhánh `bidding` (Câu hỏi còn mở 3).
Các luật lát này cần được chép dưới đây; số mục là của tệp đó.

- **Một chủ cho mỗi dữ kiện hình ảnh (§1).** Màu, chữ, bo góc, breakpoint lấy từ theme
  antd trong `@dw/ui`; Tailwind chỉ làm bố cục. Breakpoint Tailwind bằng antd
  (576/768/992/1200/1600).
- **Một chủ cho thông báo (§1):** `App.useApp()`. Không sonner, không `message.*`
  tĩnh.
- **Mỗi vùng mỗi trạng thái (§4):** một bảng mã lỗi → trạng thái trong thành phần dùng
  chung. Cấm 403 khi server nói không tìm thấy; `entitlement_denied` không phải 403;
  lỗi mạng là mất mạng, không phải lỗi.
- **Điều người xem không được thấy không tới trình duyệt (§6):** ô khóa ghi "Đã ẩn",
  không "0", không "—"; một thành phần che dùng chung cho giá, dữ liệu hạn chế và
  quyền hỗ trợ.
- **Giờ và tiền (§8):** một formatter mỗi loại; giờ trước ngày; hạn chỉ có ngày không
  qua `new Date(iso)`; ô chọn giờ đọc theo giờ Việt Nam; "chưa rõ" khác "không có";
  "đ", không "₫".
- **Bố cục (§12):** danh sách bề rộng có một chủ là `apps/web/playwright.config.ts`,
  ít nhất 320px và hai phía 992px, cộng một project múi giờ khác Việt Nam. Vùng chạm
  tối thiểu 24×24. Tương phản chữ 4,5:1.

Mỗi chốt chặn có một test đỏ khi gỡ chốt (`failure-modes.md` #3):

| Chốt                                                        | Ticket | Test đỏ khi gỡ                                                                    |
| ----------------------------------------------------------- | ------ | --------------------------------------------------------------------------------- |
| Thứ tự layer antd/Tailwind                                  | 02     | Playwright `e2e/antd-shell.spec.ts`: padding Tailwind thua antd                   |
| Tailwind `lg` = antd `lg`                                   | 02     | Playwright ở 991 và 992px                                                         |
| Chỉ `lib/dates.ts` định dạng giờ                            | 03     | luật ESLint cấm `toLocale*String`, `Intl.DateTimeFormat`, `import dayjs` nơi khác |
| Chuỗi giờ thiếu múi bị từ chối                              | 03     | vitest: `formatInstant("2026-10-14T09:00:00")` ném lỗi                            |
| Hạn chỉ có ngày không lùi ngày phía tây UTC                 | 03, 05 | vitest với `TZ=America/Los_Angeles`; Playwright project múi giờ                   |
| Không "₫"; số lẻ mơ hồ bị từ chối                           | 04     | vitest; luật ESLint cấm `currency: "VND"` ngoài `lib/money.ts`                    |
| Fixture chỉ có ở bản dev-auth                               | 05     | vitest: ở chế độ `oidc` trang gọi `notFound()`, app-frame không bỏ qua cổng       |
| Chỉ `App.useApp()` phát thông báo                           | 06     | luật ESLint cấm `sonner`, `message`/`notification` tĩnh, `Modal.confirm` tĩnh     |
| Thông báo lỗi không lộ mã máy                               | 06     | vitest: `useCachedResource` thất bại hiện `body.message`, không `"code: …"`       |
| Mọi tông và chữ đạt 4,5:1, cả sáng lẫn tối                  | 07     | vitest tính tỷ lệ từ bảng tông trong `theme.ts`                                   |
| Mã lạ không biến mất                                        | 07     | vitest: mã không có trong bảng vẫn hiện chính mã                                  |
| `MaskedValue` không mang giá trị                            | 08     | tsc: truyền `value` là lỗi kiểu; vitest: DOM không có chữ số                      |
| Mọi `ErrorCode` có trạng thái; 403 ≠ gói dịch vụ ≠ mất mạng | 09     | vitest duyệt `Object.values(ErrorCode)`; ca `entitlement_denied`, `TypeError`     |
| Test web chạy trong CI                                      | 10     | bước CI đỏ khi một test vitest, Playwright fixture hoặc spec `@api` đỏ            |
| Nút chỉ có biểu tượng có `aria-label`                       | 11     | test ESLint: `<Button icon={…} />` không `aria-label` ra lỗi                      |
| Bộ đếm ký tự theo một hàm                                   | 12     | vitest: 90% hiện "Còn N ký tự", vượt hiện "Vượt N ký tự"                          |
| Tab đầu tiên tới "Bỏ qua tới nội dung chính"                | 13     | Playwright `@ui`: gỡ liên kết thì Tab đầu tiên rơi vào nút khác                   |
| Cảnh báo trước khi phiên hết                                | 14     | vitest với đồng hồ giả: gỡ hẹn giờ thì không có hộp thoại lúc còn 2 phút          |
| Máy tối không thấy trang sáng khi tải                       | 15     | Playwright tắt JS, `colorScheme: "dark"`: nền trang và header tối                 |

Fixture dưới `/dev-login/` là đường chỉ có ở bản dev: chạy
`reviewing-deployment-security` trên thay đổi thêm nó. `NEXT_PUBLIC_AUTH_MODE` được
nướng lúc build; bản triển khai dùng `oidc`.

## Tiêu chí xong của slice

- Ticket 02–09 và 11–15 ở `Status: resolved`, mỗi ticket ghi commit và phần chứng
  minh gỡ chốt thì test đỏ dưới `## Comments`. Ticket 10 và 18 đã có quyết định của
  Đạt và đã làm theo. Ticket 16, 17 là P1, không chặn slice.
- Chạy xanh: `pnpm run format:check`, `pnpm run lint`, `pnpm run typecheck`,
  `pnpm --filter @dw/web build`, `pnpm --filter @dw/web test`,
  `pnpm --filter @dw/ui test`, `pnpm --filter @dw/web e2e` (mọi project; spec cần API
  chạy khi stack đang chạy).
- Mở `/dev-login/ui-kit` ở 320, 390, 991, 992, 1280px, sáng và tối: không cuộn ngang,
  mọi trạng thái trong spec này có mặt.
- `.claude/plans/web-ui.md` có dòng nhật ký cho lát, bundle trước/sau, và mục Open
  khớp thực tế. Merge `main` sang `bidding`.

## Phụ thuộc

- S0 không chờ lát nào khác. Ticket 01 (CI xanh) đã xong.
- Mọi lát web của sản phẩm dựng trên S0: thời điểm qua `lib/dates.ts`,
  tiền qua `lib/money.ts`, bảng nhãn của sản phẩm qua `StatusTag`, giá bị ẩn qua
  `MaskedValue`, mọi vùng tải dữ liệu qua `RegionState`. Backend của lát 1 không chờ
  S0 (D07).
- Để `MaskedValue` dùng được, API của sản phẩm phải phân biệt "bị ẩn" với "không có"
  (Câu hỏi còn mở 5).
- Cổng là approval của nền tảng (D16), nên màn Duyệt của nền tảng sẽ là màn quyết cổng
  của bản demo. Màn đó hôm nay là shadcn, chữ tiếng Anh; lát làm cổng phải dựng lại nó
  trên các phần của S0.

## Câu hỏi còn mở

1. **CI có chạy test web không?** Đạt còn nợ quyết định này (`PLAN.md`). Hôm nay CI
   chạy lint, typecheck, build cho web nhưng không chạy vitest hay Playwright, nên test
   layer của 02 và mọi test của S0 chỉ chạy trên máy người làm. Spec Playwright cần
   API (của nền tảng và của mọi context, như test âm "trường bị ẩn không có trong DOM
   lẫn phản hồi mạng") cũng chưa chạy ở đâu. Khuyến nghị: có, cả hai, ở ticket 10.
2. **Múi giờ hiển thị có theo tenant không?** `platform.tenants.timezone` là chữ tự
   do, sửa được ở Quản trị, không chỗ nào đọc (`failure-modes.md` #1). Khuyến nghị: S0
   giữ một hằng `Asia/Ho_Chi_Minh` và nhãn "giờ Việt Nam" trong `lib/dates.ts`, vì
   locale đã cố định `vi_VN` và hạn của văn bản Việt Nam theo giờ Việt Nam bất kể
   người xem ở đâu; Đạt chọn gỡ ô đó khỏi Quản trị hoặc giữ cho tới khi có sản phẩm cần
   múi khác. Không chặn S0.
3. **`ui-quality.md` chỉ có trên `bidding`.** Spec này chép các luật cần. Khuyến nghị:
   đưa một bản trung tính (bỏ ví dụ của sản phẩm) lên `main`, để agent làm ở `main`
   đọc được.
4. **Trang nền tảng viết tiếng Anh, locale là `vi_VN`, `<html lang="en">`.** Bản demo sẽ
   lẫn hai thứ tiếng ở menu ("Approvals", "Audit log") và ở các trang nền tảng. Ai dịch,
   lúc nào? Khuyến nghị: ticket 18 đổi `lang="vi"` và dịch nhãn menu nền tảng trước
   buổi demo; màn Duyệt được dựng lại ở lát làm cổng.
5. **API báo "bị ẩn" thế nào?** `MaskedValue` cần biết trường vắng vì bị ẩn chứ không
   phải vì không có. Khuyến nghị: một quy ước chung cho mọi API (ví dụ danh sách
   `redacted_fields` trong phản hồi), chốt ở lát đầu tiên trả giá.
6. **Ô chọn Sáng / Tối / Theo máy.** Design vẽ ô này trong menu người dùng, ghi "(chờ
   D07)"; D07 chốt "sáng/tối theo máy như design". S0 chỉ theo máy. Có cần cho người
   dùng tự chọn không? Nếu có: ticket 16 (P1). Phần không nháy sáng khi tải không chờ
   câu này (ticket 15).
7. **Bảng catalog và CSS của khung v3 lệch màu lỗi.** Catalog ghi `colorError`
   `#e0352b` (sáng) và `#ff453a` (tối); CSS khung dùng `#c4271e`, và ở chế độ tối tách
   nền nút `#d63a30` với chữ `#ff6b61`. Chữ trắng trên `#e0352b` đạt 4,46:1, trên
   `#ff453a` đạt 3,41:1, đều dưới 4,5:1. Spec lấy giá trị của CSS khung (D07 cho phép).

## Danh sách ticket

| #   | Ticket                                                                              | Status          | Blocked by     |
| --- | ----------------------------------------------------------------------------------- | --------------- | -------------- |
| 01  | [CI xanh trên `main`](issues/01-ci-green.md)                                        | resolved        | —              |
| 02  | [Shell antd: theme A, provider, AppShell, thứ tự layer](issues/02-antd-shell.md)    | resolved        | 01             |
| 03  | [`lib/dates.ts` theo giờ Việt Nam](issues/03-lib-dates.md)                          | ready-for-agent | 02             |
| 04  | [`lib/money.ts`](issues/04-lib-money.md)                                            | ready-for-agent | 02, 05         |
| 05  | [Hạ tầng kiểm thử UI: bề rộng, múi giờ, fixture](issues/05-ui-test-harness.md)      | ready-for-agent | 02, 03         |
| 06  | [Thông báo qua `App.useApp()`, gỡ sonner](issues/06-app-feedback.md)                | ready-for-agent | 02, 05         |
| 07  | [Theme v3 còn lại, tông trạng thái, `StatusTag`](issues/07-status-tones-and-tag.md) | ready-for-agent | 02, 05         |
| 08  | [`PageHeader`, `MaskedValue`, `AbsentValue`](issues/08-page-header-and-cells.md)    | ready-for-agent | 05, 07         |
| 09  | [`RegionState` và băng mất mạng](issues/09-region-state-and-offline.md)             | ready-for-agent | 03, 05, 07     |
| 10  | [CI chạy test web](issues/10-web-tests-in-ci.md)                                    | needs-info      | 05             |
| 11  | [Quy ước nút](issues/11-button-conventions.md)                                      | ready-for-agent | 05, 07         |
| 12  | [Quy ước trường: nhãn, gợi ý, lỗi, bộ đếm, ô giờ](issues/12-field-conventions.md)   | ready-for-agent | 03, 04, 05, 07 |
| 13  | [Bỏ qua tới nội dung chính, vùng `main`](issues/13-skip-link-and-main.md)           | ready-for-agent | 05             |
| 14  | [Cảnh báo phiên sắp hết hạn](issues/14-session-expiry-warning.md)                   | ready-for-agent | 03, 06         |
| 15  | [Chế độ tối không nháy sáng khi tải](issues/15-dark-mode-before-hydration.md)       | ready-for-agent | 05             |
| 16  | [Ô Sáng / Tối / Theo máy (P1)](issues/16-color-mode-choice.md)                      | needs-info      | 15             |
| 17  | [Bảng lệnh Ctrl K (P1)](issues/17-command-palette.md)                               | ready-for-agent | 05             |
| 18  | [`lang="vi"` và nhãn menu nền tảng](issues/18-lang-vi-and-nav-labels.md)            | needs-info      | 02             |
