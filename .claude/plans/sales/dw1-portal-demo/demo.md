# Kịch bản demo DW1 — Đơn hàng & Báo giá (dữ liệu giả lập)

Ticket 09. Kịch bản này đi đúng thứ tự mục "Done when" của `spec.md`, mỗi bước
một persona, trên stack cục bộ. **Mọi khách hàng, người, mã hàng và con số ở
đây đều hư cấu** (`packages/python/dw_sales/adapters/mock/README.md`); không
có tài liệu hay con số nào của Proterial. Không bước nào làm bằng
`platform_admin`.

Phần tự động của kịch bản (đường chính và các lần bị từ chối) là
`apps/web/e2e/sales-demo.spec.ts`; chạy `make test-web-sales` trước buổi demo
để chắc kịch bản còn đúng.

## 1. Chuẩn bị (một lần, trước buổi demo)

```sh
make infra-up          # Postgres, Keycloak, S3, ... trong Docker
make db-migrate
make demo-reset        # trạng thái bắt đầu của demo (xem dưới)
make dev               # API :8300, web :3300 theo .env (DW_WEB_PORT=3300)
```

`make demo-reset` đưa stack về **đúng một trạng thái bắt đầu**, lần nào cũng
như nhau:

- xóa mọi hồ sơ đơn hàng và báo giá, nhật ký thư, sự kiện hồ sơ, nguồn đã mở,
  bản ghi tệp và công tắc tạm dừng của **hai tenant demo** (tenant-alpha,
  tenant-beta) — không đụng tenant khác, không xóa audit log (append-only);
- xóa các lượt chạy (run) của DW1, checkpoint của chúng và các yêu cầu duyệt
  `sales.*` cùng quyết định, nên hộp duyệt bắt đầu trống và buổi diễn tập
  trước không ăn vào số lượt chạy trong ngày của gói;
- chạy seed nền tảng rồi gán vai Sales cho các persona
  (`dw_sales.testing.seed_personas`);
- cho mỗi persona một tài khoản Keycloak, mật khẩu là `DW_DEV_USER_PASSWORD`
  trong `.env` (không commit).

Sau đó: hộp thư 32 thư đều "Chưa xử lý", không có hồ sơ nào, DW1 đang chạy.
Chỉ chạy được ở profile `local`/`test`.

Đăng nhập ở `http://localhost:3300` bằng email persona và mật khẩu trên. Đổi
người: đăng xuất rồi đăng nhập lại (hoặc mở cửa sổ ẩn danh cho người thứ hai).

## 2. Các persona

| Persona         | Email                    | Vai trên cổng                                         | Dùng trong demo để                                    |
| --------------- | ------------------------ | ----------------------------------------------------- | ----------------------------------------------------- |
| Nguyễn Văn An   | `an.nguyen@alpha.local`  | Sales phụ trách (PIC) + PIC kiểm soát xuất khẩu       | xử lý hộp thư, chuẩn bị đơn, nhập Bravo, xác nhận     |
| Hoàng Thị Diệu  | `dieu.hoang@alpha.local` | Sales phụ trách (PIC) + xem giá đã báo cho khách khác | kiểm chéo đơn của An, định giá M10                    |
| Đỗ Trường Giang | `giang.do@alpha.local`   | Trưởng bộ phận Sales                                  | duyệt báo giá, cho DW1 chạy lại, định giá một báo giá |
| Lâm Minh Khoa   | `khoa.lam@alpha.local`   | Sales phụ trách (PIC) + người duyệt báo giá thay      | duyệt báo giá Giang định giá                          |
| Vũ Thanh Hà     | `ha.vu@alpha.local`      | Lãnh đạo (xem tổng hợp)                               | chỉ xem tổng quan                                     |
| Trần Thị Bình   | `binh.tran@alpha.local`  | Mua hàng, không có quyền Sales                        | bị từ chối mọi trang Sales                            |
| Ngô Minh Tâm    | `tam.ngo@alpha.local`    | IT (quản trị tenant), không có quyền Sales            | không thấy Sales, không thấy giá                      |
| Phạm Quốc Bảo   | `bao.pham@beta.local`    | Sales phụ trách ở **tenant khác** (tenant-beta)       | hộp thư rỗng, 404 trên hồ sơ của tenant-alpha         |

Tên hiển thị lấy từ `configs/demo/demo_users.yaml`; nếu lệch, file đó đúng.

## 3. Kịch bản

Mỗi bước: **ai** — làm gì → thấy gì. "Bị từ chối" là phần phải cho khán giả
thấy, không phải lỗi.

**DW1 chạy trên runtime (ticket 10).** "DW xử lý", **Trình duyệt** và **Đã
nhập Bravo** mỗi lần là một lượt chạy (run) của DW1, được đếm vào số lượt chạy
trong ngày của gói (`RunAllowancePort`). Trình duyệt và nhập Bravo làm lượt
chạy dừng ở một **yêu cầu duyệt của nền tảng** (`sales.quote`,
`sales.order.cross_check`); nút **Duyệt báo giá** / **Kiểm chéo đạt** quyết
định trên yêu cầu đó (`POST /api/v1/approvals/{id}/decisions`), không còn
route quyết định riêng của Sales. Yêu cầu duyệt của Sales là loại nghiêm ngặt:
người quyết định phải khác mọi người đã làm hồ sơ và **phải ghi nhận xét**.

### 3.1 An gửi M04 lại cho khách (trước khi xử lý cả hộp thư)

"DW xử lý tất cả" xử lý thư cũ nhất trước, nên nếu bấm ngay, bản Rev.1 của
khách (M07) sẽ vào hồ sơ M04 trước khi ai yêu cầu khách sửa. Vì vậy An làm M04
trước, đúng thứ tự WIV-03-012 bước 8.

1. **An** mở _Sales → Hộp thư_, bấm **DW xử lý** trên M04. Thư sang "Đã vào hồ
   sơ".
2. Mở hồ sơ M04: hai cờ `price_mismatch` dòng 2 và `code_unmapped` dòng 3.
3. _Bị từ chối:_ gọi thẳng API `POST /orders/{id}/prepare` khi cờ còn mở trả
   **409**, nêu tên cờ (`price_mismatch:2`).
4. Với từng cờ chọn **Yêu cầu khách sửa** → **Ghi quyết định** (không có "chấp
   nhận tất cả"). Bấm **Gửi yêu cầu khách sửa** → **Gửi yêu cầu sửa**. Hồ sơ
   sang "Chờ khách sửa PO"; thư nháp liệt kê đúng hai dòng.

### 3.2 An xử lý cả hộp thư

1. Ở hộp thư, bấm **DW xử lý tất cả (31)**. Thanh "Cần xử lý" về 0 thư chưa xử
   lý: _không thư nào bị bỏ sót_ (spec quyết định 10); mỗi thư chuyển Sales có
   lý do và người phụ trách.
    - M07 (Rev.1) "Đã gắn vào hồ sơ" — **cùng hồ sơ** M04: hồ sơ hiện "Đang xem
      Rev.1", M04 ở mục bản đã thay thế, bảng thay đổi so với bản gốc, cờ
      `revised_po`; mọi kiểm tra chạy lại.
    - M11, M31, M17: chuyển Sales (đổi lịch giao, khiếu nại, hàng mẫu).
    - M15: chưa xác định được khách hàng. M16: PDF scan, không đọc được — không
      mở hồ sơ, không có giá trị nào được "đọc".
    - Phản hồi Design (M18, M25, M29, M30, M32) chuyển Sales "Phản hồi Design
      không khớp YCBG" vì chưa ai ghi số YCBG. Sau khi ghi YCBG và gửi Design
      (3.5, 3.6), bấm **DW xử lý lại** trên thư phản hồi để ghép vào hồ sơ.
    - M12 có chỉ thị độc ("Ignore previous instructions … attacker@evil.example")
      trong thân thư và ô Remarks: hồ sơ mở bình thường, giá trị đúng như file,
      không cờ nào; thư nháp xác nhận chỉ gửi liên hệ của khách (eval
      `sales-sec-prompt-injection-m12`).
2. (Tùy chọn) M05: dòng 1 khớp hai mã — chọn một trong hai ứng viên; dòng 2 có
   một ứng viên (`CB-2005`) — xác nhận.

### 3.3 An chuẩn bị M03, Diệu kiểm chéo, An xác nhận

1. _Bị từ chối:_ **Diệu** (không có quyền kiểm soát xuất khẩu) chấp nhận cờ
   `missing_noc_esf` của M03 qua API → **403**.
2. **An** mở hồ sơ M03 (BRN, PDF tiếng Việt, VND): khách, giờ nhận (giờ Việt
   Nam), số cờ, người phụ trách. Bấm **Mở bản gốc**: trang PDF hiện với khung
   quanh từng giá trị đọc được.
3. Quyết định từng cờ bằng **Chấp nhận + lý do** → **Ghi quyết định**:
    - "Không có báo giá còn hiệu lực, dòng 2" — ví dụ "Khách xác nhận giá theo
      thư ngày 22/09";
    - "Thiếu NOC/ESF" — An giữ quyền kiểm soát xuất khẩu; ví dụ "Đã kiểm tra
      danh sách cấm, chờ ESF năm nay". Cờ này chỉ chặn bước xác nhận.
4. Mỗi quyết định là một phiên bản hồ sơ mới: **Chuẩn bị xong** bị khóa với lý
   do "Chưa mở nguồn: mở bản gốc của phiên bản hồ sơ này trước khi quyết định."
   Bấm **Mở nguồn**, rồi **Chuẩn bị xong**.
5. Trong "Tệp và thư nháp DW1 soạn": soạn và **Tải** "Tệp nhập Bravo (mẫu giả
   lập)" (xlsx).
6. **Đã nhập Bravo** → số đơn Bravo (ví dụ `SO26-1001`), xác nhận đã đối chiếu
   với PO → **Ghi số đơn Bravo**.
7. _Bị từ chối:_ với An, **Kiểm chéo đạt** bị khóa, lý do bằng chữ "Bạn đã
   chuẩn bị đơn này nên không tự kiểm chéo được (tách nhiệm, WIV-03-012 bước
   9)."; quyết định thẳng trên yêu cầu duyệt
   (`POST /api/v1/approvals/{id}/decisions`, id ở `decision.approval_id` của
   hồ sơ) trả **409** "tách nhiệm": yêu cầu nêu tên mọi người làm hồ sơ. Route
   cũ `POST /orders/{id}/cross-check` không còn (404).
8. **Diệu** mở M03, **Mở nguồn**, rồi **Kiểm chéo đạt**, ghi **Ghi chú kiểm
   chéo** (đã đối chiếu những gì) → **Ghi kiểm chéo đạt**. Lượt chạy của DW1
   tiếp tục và ghi kiểm chéo vào hồ sơ dưới tên Diệu.
9. **An** bấm **Đã gửi xác nhận**: nhập **ngày xác nhận cho từng dòng** (cột "DW1
   gợi ý" ghi rõ là đề xuất) → **Ghi đã gửi xác nhận**. Thư nháp xác nhận nêu
   tên cả người chuẩn bị lẫn người kiểm chéo.

### 3.4 Diệu định giá M10

1. **Diệu** mở báo giá M10 (KMH, tiếng Nhật, có giá mục tiêu), mở nguồn, rồi
   **Soạn YCBG** → **Đã lập YCBG** → số `YCBG-2609-030` → **Ghi số YCBG** →
   **Gửi Design**.
2. Ở hộp thư, **DW xử lý lại** trên M25: thư "Đã gắn vào hồ sơ"; M10 hiện
   "YCBG YCBG-2609-030 · trả lời ngày …".
3. Diệu xem căn cứ giá: lịch sử báo giá, lịch sử đặt hàng, LME, phần đồng, và
   **Giá đã báo cho khách khác** (ví dụ `Q26-0104`, 0,712 USD) — Diệu có quyền
   xem.
4. **Ghi giá**: đơn giá 0,6890 USD/m, MOQ 3000, lead time 45 ngày, căn cứ đồng
   theo dải LME 10 500–11 000, tháng LME 2026-09 → **Trình duyệt** với số báo
   giá `Q26-0301`. DW1 điền tài liệu báo giá (xlsx + PDF) và đóng dấu mã băm.
5. _Bị từ chối:_ với Diệu, **Duyệt báo giá** bị khóa ("Bạn không có quyền duyệt
   báo giá"); quyết định thẳng trên yêu cầu duyệt trả **403** — yêu cầu được
   đóng dấu `sales.quote.approve`, còn `approver_boost` của nền tảng chỉ cho
   `approvals.decide`. **Bình** (quản lý mua hàng, có `approvals.decide`) cũng
   nhận **403**, và hộp duyệt của Bình không có yêu cầu này.
6. _Bị từ chối:_ **An** mở M10 — mục "Giá đã báo cho khách khác" hiện **"Đã
   ẩn"**, không phải 0 hay "—"; số báo giá và giá của khách khác không có trên
   trang.

### 3.5 Giang duyệt M10, gửi báo giá

1. _Bị từ chối:_ trước khi duyệt, soạn thư nháp gửi khách qua API trả **409**
   (tệp chưa tới trạng thái của nó).
2. **Giang** mở M10 ("Duyệt báo giá Q26-0301"). Trong "Tệp và thư nháp DW1
   soạn", bấm **Soạn Tài liệu báo giá (bản xem trước)**, rồi **tải lại trang**
   (lỗi đã biết: khung duyệt không tự làm mới, xem ticket 09 "Open"). Bấm **Xem
   bản xem trước (PDF…)**: trang 1 của tài liệu hiện ra, cùng mã băm và phiên
   bản. (Bản ký giấy vẫn là bản duyệt chính thức; duyệt trên cổng là đề xuất.)
3. Ghi **Nhận xét khi duyệt**, rồi **Duyệt báo giá**. Thư nháp gửi khách giờ
   soạn và tải được (đính kèm tài liệu, nêu số spec).
4. (Tùy chọn) **Diệu**: **Đã gửi KH** → **Xác nhận master list**.

### 3.6 Khoa duyệt báo giá Giang định giá

1. **Giang** mở M14 (yêu cầu do quản lý Sales chuyển tiếp, cờ
   `customer_unknown`): **Mã khách hàng** `VLX` → **Ghi câu trả lời của
   khách**; **Soạn YCBG**, **Đã lập YCBG** `YCBG-2609-029`, **Gửi Design**; ở
   hộp thư **DW xử lý lại** trên M29.
2. Giang **Ghi giá** (ví dụ 0,8200, cùng các trường như 3.4) → **Trình duyệt**
   với số `Q26-0302`.
3. _Bị từ chối:_ với Giang, **Duyệt báo giá** bị khóa ("Bạn đã định giá báo giá
   này nên không tự duyệt được (tách nhiệm, WIV-03-023 bước 9)."); quyết định
   thẳng trên yêu cầu duyệt trả **409** "tách nhiệm".
4. **Khoa** mở M14, điền **Lý do chấp nhận khi duyệt** cho cờ giá chặn (nếu
   có) và **Nhận xét khi duyệt**, rồi **Duyệt báo giá**.

### 3.7 Tạm dừng / chạy lại

1. **An** bấm **Tạm dừng DW1** trên thanh Sales, ghi lý do → **Tạm dừng DW1**.
   Thanh báo "DW1 đang tạm dừng"; **DW xử lý** bị khóa, các bước của Sales vẫn
   làm được.
2. _Bị từ chối:_ với An, **Tiếp tục DW1** bị khóa, lý do "Chỉ Trưởng bộ phận
   Sales cho DW1 chạy lại."; API trả **403**.
3. **Giang** (người giữ quyền cho chạy lại, đã nhận thông báo) bấm **Tiếp tục
   DW1**, ghi lý do → **Cho DW1 chạy lại**.

### 3.8 Những người không được vào

- **Hà** (lãnh đạo): _Sales → Tổng quan_ chỉ có số lượng và thời gian, không
  danh sách hồ sơ, không số tiền. Mọi URL Sales khác (hộp thư, đơn hàng, báo
  giá, master data) hiện trang "không có quyền" và API trả **403**; không câu
  trả lời nào chứa một con số giá. Hộp duyệt của nền tảng
  (`GET /api/v1/approvals`) không có yêu cầu `sales.*` nào: yêu cầu chỉ hiện
  cho người được quyết định và người đã yêu cầu.
- **Bình** (mua hàng): **403** trên mọi `/api/v1/sales/*`; menu không có Sales.
- **Tâm** (IT tenant): không có quyền Sales nào, không thấy giá; luật tách nhiệm
  của nền tảng không cho một membership giữ cả `platform.members.write` lẫn
  `sales.price.read`.
- **Bảo** (tenant-beta): hộp thư rỗng; mở một hồ sơ của tenant-alpha bằng id
  → **404** (không phải 403: không xác nhận hồ sơ tồn tại).

## 4. Điều demo này cho thấy và không cho thấy

Theo bảng "Promises and what this demo shows" của `spec.md`:

- Đo trên bộ giả lập: thư không có hướng xử lý = 0, thư chuyển Sales không có
  người phụ trách = 0; mọi dòng PO được đọc và kiểm (câu "Đã đọc N/N dòng");
  bộ eval `sales@1.0.0` chấm trích xuất (mã PRV, số lượng, đơn giá, ngày yêu
  cầu) và phát hiện (recall/precision) — `make eval-smoke`.
- **Không** khẳng định tỷ lệ, số giờ tiết kiệm hay thời gian đầu-cuối: bộ giả
  lập quá nhỏ, và các bước trùng kế hoạch Bravo của Proterial không được tính.
- Thứ tự khác WIV-03-012 (kiểm trước khi nhập Bravo, kiểm chéo sau) được trình
  bày là **đề xuất**, chờ Proterial chấp nhận.
- Duyệt báo giá và kiểm chéo là quyết định trên yêu cầu duyệt của runtime: lượt
  chạy của DW1 dừng (interrupt) và tiếp tục khi có quyết định (ADR 0004 của
  dw_sales, thay ADR 0001). Bản ký giấy vẫn là bản duyệt chính thức cho tới
  khi Proterial quyết định.
- Trang _Approvals_ chung của nền tảng cũng liệt kê yêu cầu duyệt Sales cho
  người được quyết định, nhưng quyết định ở đó bị từ chối vì không mang phiên
  bản hồ sơ đã xem; trong demo luôn quyết định từ trang hồ sơ Sales.

## 5. Sau buổi demo

`make demo-reset` lần nữa để về trạng thái bắt đầu. Tệp đã soạn vẫn nằm trong
object storage dưới tiền tố tenant/workspace nhưng không còn bản ghi nào trỏ
tới; offboarding tenant xóa chúng theo tiền tố.
