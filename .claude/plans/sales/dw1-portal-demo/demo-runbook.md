# Runbook demo DW1 trên portal — từ số 0, cho người chưa dùng bao giờ

Mục tiêu: anh mở máy lên, làm theo từng dòng, là demo được **gần như toàn bộ
DW1** (luồng nghiệp vụ + config + quản trị + các màn "hay ho") một cách mượt,
dễ hiểu cho khán giả là dân IT. Mọi dữ liệu ở đây **giả lập** (tenant FDX demo),
không có gì của Proterial, không nối hệ thống thật.

Đây là bản "cầm tay chỉ việc", bổ sung cho kịch bản gốc `demo.md` (đầy đủ 11
bước) và test tự động `apps/web/e2e/sales-demo.spec.ts` (nguồn chuẩn của nhãn
nút).

---

## 0. Nguyên tắc vàng — đọc 1 phút này trước

**Không có "1 account làm được mọi thứ".** Nền tảng chặn ở 2 tầng, cố ý, vì đây
là điểm bán hàng (chống gian lận — không ai một mình làm trọn chuỗi):

1. **Trigger trong database** từ chối gộp *quyền quản trị người dùng* với *quyền
   xem giá* trên cùng một tài khoản. Muốn gộp phải sửa migration = **sửa luật**.
2. **Tầng hồ sơ**: người đã chuẩn bị đơn **không tự kiểm chéo**, người đã định
   giá **không tự duyệt** — gọi thẳng API vẫn trả 409. Nằm trong code guard.

→ Nên ta dùng **1 account "lái" quyền rộng** (làm ~95%) + **2 ghế phụ mở sẵn ở
cửa sổ khác** (không đăng xuất, không loạn):

| Vai | Account | Dùng để |
| --- | --- | --- |
| **Lái** (cửa sổ chính) | **An** (`an.nguyen`) + cấp thêm quyền ở bước 2 | làm hết luồng + toàn bộ config Sales |
| **Ghế duyệt** (cửa sổ 2) | **Giang** (`giang.do`) | kiểm chéo đơn, duyệt báo giá, duyệt quy tắc, cho DW1 chạy lại |
| **Ghế admin** (cửa sổ 3) | **Chi** (`chi.le`) | quản trị người dùng, phân quyền, tách nhiệm, workspace |

Cách này **không sửa luật** — chỉ cấp các bộ quyền vốn hợp lệ cho An.

**AI để TẮT** cho buổi đầu (chạy mượt, không cần GPU). Phần bật AI ở mục 7.

---

## 1. Dựng stack (làm 1 lần, ~10 phút, lần đầu lâu hơn vì build image)

Bật Docker Desktop trước. Rồi ở thư mục `dw-proterial`, chạy lần lượt:

```sh
make infra-up          # Postgres, Keycloak, S3, reader... trong Docker
make db-migrate        # tạo schema
make demo-reset        # về trạng thái bắt đầu: 45 thư chưa xử lý, chưa có hồ sơ
DW_WORKER_SALES_INBOX_LANE=false make dev   # API :8300, web :3300, worker
```

- Lần đầu build image `reader` (LibreOffice, Tesseract) mất vài phút — bình thường.
- `DW_WORKER_SALES_INBOX_LANE=false`: tắt làn tự-xử-lý để anh **tự bấm** theo thứ
  tự demo. (Muốn xem DW tự chạy thì bỏ biến này — xem mục 6.)
- Cổng: **web = http://localhost:3300**, API = http://localhost:8300.
- `make demo-reset` xóa sạch hồ sơ demo và seed lại — chạy lại **trước mỗi buổi**.

> Khuyến nghị: chạy `make test-web-sales` một lần trước buổi demo. Nếu nó xanh,
> nghĩa là toàn bộ nút bấm trong kịch bản còn đúng.

---

## 2. Mở 3 cửa sổ và đăng nhập (đây là phần chống-loạn)

Ý tưởng: **mỗi vai một cửa sổ, mở sẵn từ đầu, không bao giờ đăng xuất.** Dùng chế
độ cửa sổ tách biệt của Chrome để 3 phiên không đè nhau:

- **Cửa sổ 1 (Lái)** — cửa sổ thường.
- **Cửa sổ 2 (Duyệt)** — một *profile* Chrome khác, hoặc cửa sổ **ẩn danh #1**.
- **Cửa sổ 3 (Admin)** — cửa sổ **ẩn danh #2** (một cửa sổ ẩn danh mới, không chung
  với #1).

> Mẹo: cửa sổ ẩn danh dùng chung phiên với nhau nếu mở cùng nhóm. Nếu bị lẫn,
> dùng **Chrome Profiles** (biểu tượng avatar → "Add" tạo 3 profile: Lái/Duyệt/
> Admin). Chắc chắn nhất.

Ở **mỗi** cửa sổ, vào `http://localhost:3300` → app chuyển sang **trang đăng
nhập Keycloak**. Đăng nhập **bằng EMAIL** (realm bật `loginWithEmailAllowed`),
mật khẩu là `DW_DEV_USER_PASSWORD` trong `.env`:

- Cửa sổ 1 (Lái) → `an.nguyen@alpha.local`
- Cửa sổ 2 (Duyệt) → `giang.do@alpha.local`
- Cửa sổ 3 (Admin) → `chi.le@alpha.local`

> **Dùng EMAIL, đừng dùng username.** Username Keycloak của `chi.le` là **`chi`**
> (tài khoản có sẵn trong realm import; seed chỉ đặt lại mật khẩu, không đổi
> username), nên gõ `chi.le` sẽ **không vào được** — gõ **email** là chắc cho cả
> ba.
>
> (Bản cục bộ còn có trang một-chạm `/dev-login` liệt kê sẵn các persona: nếu nó
> hiện thì bấm **"Đăng nhập"** cạnh người cần, không cần mật khẩu; nếu nó chuyển
> thẳng sang Keycloak thì dùng email như trên.)

### 2b. Cấp quyền rộng cho account Lái (An) — làm 1 lần sau mỗi `demo-reset`

Đây vừa là bước chuẩn bị, **vừa là demo luôn phần "tạo tài khoản & phân quyền"**.

Ở **Cửa sổ 3 (Chi)**:

1. Vào **`/admin`** (menu *Quản trị → Vai trò và quyền*). Thấy thẻ **"Thành viên"**.
2. Tìm dòng **Nguyễn Văn An**. Bấm **"Bộ quyền bổ sung"** (link nhỏ có hình khiên).
3. Tích thêm các bộ quyền (theo chức năng — tên hiển thị trên màn):
   - **Xem giá đã báo cho khách khác** (để An thấy căn cứ giá),
   - **Duyệt báo giá thay** (để An duyệt báo giá của *người khác*),
   - **Đề xuất/sửa quy tắc** (để An vào được phần config Sales).
   - (An đã sẵn có *Kiểm soát xuất khẩu* — không cần tích lại.)
4. Bấm **"Lưu bộ quyền"**.
   > Nếu hệ thống từ chối một bộ nào đó (báo lỗi tách nhiệm), bỏ đúng bộ đó ra,
   > phần còn lại vẫn lưu được — đó chính là luật tách nhiệm đang chạy.
5. Quay lại **Cửa sổ 1 (An)**, **tải lại trang** (hoặc đăng nhập lại qua
   `/dev-login`) để quyền mới có hiệu lực.

> Giải thích cho khán giả tại đây: "Quyền cấp theo **vai** và **bộ quyền**. Có
> những thứ nền tảng **không cho gộp** vào một người — ví dụ quyền quản trị với
> quyền xem giá — để không ai một mình thao túng được." Đó là lý do phần quản trị
> vẫn ở tài khoản Chi riêng.

Muốn khoe thêm **tạo tài khoản mới**: ở thẻ Thành viên bấm **"Thêm người"** →
nhập tên/email → chọn **Vai** → tạo xong hệ thống hiện **mật khẩu tạm** một lần
(đưa cho người đó để họ tự đăng nhập). Đây là đường tạo tài khoản thật (không cần
qua `/dev-login`).

---

## 3. Luồng nghiệp vụ end-to-end (phần xương sống)

Mỗi dòng: **[cửa sổ] người — vào đâu → bấm gì → thấy gì.** "Bị từ chối" là phần
phải cho khán giả thấy, **không phải lỗi**.

> **Đi đúng vòng đời thật — KHÔNG demo ngược.** Khách **hỏi giá → DW báo giá**
> (3.1) → khách **gửi PO (file SO)** → **DW nhập & kiểm đơn** (3.2, 3.3).
> - DW **nhập SO từ file SO khách gửi, không "sinh" SO từ báo giá** (Đạt 25/11):
>   về kỹ thuật không bấm "kéo dữ liệu từ báo giá". Nhưng về **nghiệp vụ, báo giá
>   vẫn có trước**.
> - Quan hệ "phải có báo giá trước" **nhìn thấy được**: khi kiểm đơn, DW **đối
>   chiếu PO với báo giá còn hiệu lực** (bước O6) — không có thì ra cờ **"Không có
>   báo giá còn hiệu lực"** (3.3). Nhớ chỉ cái cờ này cho khán giả để nối mạch.
> - (Lưu ý nội bộ, chưa vào code) Bravo còn cần YCBG/báo giá/master-data tồn tại
>   trước mới tạo được SO — là **giả định cần kiểm bằng trace/layout** cho gateway
>   (ticket 68), không bịa vào demo.

### 3.1 Báo giá: YCBG → Design → định giá → **duyệt (ghế duyệt)**

**[Cửa sổ 1 — An]**
1. Hộp thư → **"DW xử lý thư M10"** → mở hồ sơ báo giá (`/sales/quotes/<id>`).
2. **"Mở bản gốc"** → **"Soạn YCBG"** → **"Đã lập YCBG"** → gõ số `YCBG-2609-030`
   → **"Ghi số YCBG"** → **"Gửi Design"**.
3. Về Hộp thư, trên dòng **M25** bấm **"DW xử lý lại"** (đây là phản hồi của
   Design, giờ ghép được vào hồ sơ nhờ số YCBG). Quay lại hồ sơ M10: thấy
   *"YCBG YCBG-2609-030 · trả lời ngày…"* và **căn cứ giá** (LME, đồng, **giá đã
   báo cho khách khác** — An thấy được vì đã cấp quyền ở bước 2b).
4. **"Ghi giá"**: đơn giá `0,6890`, MOQ `3000`, lead time `45`, căn cứ đồng theo
   dải LME `10500`–`11000`, tháng LME `09/2026` → **"Trình duyệt"** với số báo
   giá `Q26-0301`.
5. **Bị từ chối (phải khoe):** nút **"Duyệt báo giá"** của An **bị khóa** —
   *"Bạn đã định giá báo giá này nên không tự duyệt được (tách nhiệm)."*

**[Cửa sổ 2 — Giang]** (ghế duyệt)
6. Mở hồ sơ M10, bấm **"Soạn Tài liệu báo giá (bản xem trước)"** nếu có →
   **"Xem bản xem trước (PDF…)"** (xem trang 1 + mã băm) → ghi **"Nhận xét khi
   duyệt"** → **"Duyệt báo giá"**. Xong có thư nháp gửi khách để tải.

> Muốn khoe thêm *An cũng có quyền duyệt*: ở một báo giá do **người khác** định
> giá, An bấm "Duyệt báo giá" được — chỉ không duyệt được cái của **chính An**.

### 3.2 Đơn hàng: đọc PO → kiểm tra → yêu cầu khách sửa

Giờ mới tới PO (sau khi đã báo giá ở 3.1).

**[Cửa sổ 1 — An]**
1. Vào **`/sales/inbox`** (menu *Sales → Hộp thư*). Tìm dòng **M04**, bấm
   **"DW xử lý thư M04"**. Thư chuyển "Đang chờ DW1" → vài giây sau "Đã tạo hồ sơ".
   > Giải thích: bấm là **xếp việc cho worker**; worker đọc file đính kèm trong
   > sandbox cách ly, rồi mở hồ sơ. (Vì vậy worker phải đang chạy — mục 1.)
2. Bấm **"Mở đơn hàng"** để vào hồ sơ. Thấy **2 cờ**: "Đơn giá lệch báo giá, dòng
   2" (DW **đối chiếu PO với báo giá** — chính là quan hệ "có báo giá trước") và
   "Mã chưa có trong convert list, dòng 3".
3. Bấm **"Mở bản gốc"** → trang PDF hiện ra với **khung bao quanh từng giá trị
   DW đọc được**. Đóng lại.
4. Với **từng cờ**: chọn **"Yêu cầu khách sửa"** → **"Ghi quyết định"** (lưu ý:
   không có nút "chấp nhận tất cả" — cố ý, duyệt từng cái).
5. Bấm **"Gửi yêu cầu khách sửa"** → trong hộp thoại bấm **"Gửi yêu cầu sửa"**.
   Hồ sơ sang **"Chờ khách sửa PO"**; có thư nháp liệt kê đúng 2 dòng để tải.

### 3.3 Đơn hàng khác: chuẩn bị → **kiểm chéo (ghế duyệt)** → xác nhận

Đây là chỗ cho thấy **tách nhiệm**: người chuẩn bị ≠ người kiểm chéo.

**[Cửa sổ 1 — An]**
1. Ở Hộp thư, **"DW xử lý thư M03"** → **"Mở đơn hàng"**. (M03 là PO tiếng Việt,
   khách BRN, có cờ **"Thiếu NOC/ESF"** đang **giữ đơn**.)
2. Bấm **"Mở bản gốc"** xem trang PDF có khung đọc.
3. Quyết định các cờ bằng **"Chấp nhận + lý do"** → **"Ghi quyết định"**:
   - "Không có báo giá còn hiệu lực, dòng 2" — lý do ví dụ *"Khách xác nhận giá
     theo thư 22/09"*. (Đây là cờ thể hiện "phải có báo giá trước".)
   - "Thiếu NOC/ESF" — lý do ví dụ *"Đã kiểm tra danh sách cấm, chờ ESF năm nay"*.
     (An có quyền kiểm soát xuất khẩu nên xác nhận được cờ này.)
4. Nút **"Chuẩn bị xong"** đang khóa với lý do *"Chưa mở nguồn…"*. Bấm **"Mở
   nguồn"**, rồi bấm **"Chuẩn bị xong"**.
5. Trong "Tệp và thư nháp DW1 soạn": bấm soạn và **"Tải"** *"Tệp nhập Bravo (mẫu
   giả lập)"* (file .xlsx). → Đây là bản mô phỏng; **DW chưa ghi vào Bravo thật**.
6. Bấm **"Đã nhập Bravo"** → gõ số đơn ví dụ `SO26-1001` → tích *"Tôi đã đối
   chiếu…"* → **"Ghi số đơn Bravo"**.
7. **Bị từ chối (phải khoe):** nút **"Kiểm chéo đạt"** của An **bị khóa**, lý do
   bằng chữ: *"Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (tách nhiệm…)."*

**[Cửa sổ 2 — Giang]** (ghế duyệt)
8. Mở đúng hồ sơ M03 đó (vào `/sales/orders`, chọn PO đó — hoặc dán cùng URL
   `/sales/orders/<id>` từ cửa sổ 1). Bấm **"Mở nguồn"**, rồi **"Kiểm chéo đạt"**,
   ghi **"Ghi chú kiểm chéo"** (đã đối chiếu gì) → **"Ghi kiểm chéo đạt"**.
   > Giang không phải người chuẩn bị nên được kiểm chéo. Lượt chạy DW tiếp tục.

**[Cửa sổ 1 — An]**
9. Quay lại hồ sơ, bấm **"Đã gửi xác nhận"** → nhập **ngày xác nhận cho từng
   dòng** → **"Ghi đã gửi xác nhận"**. Thư nháp xác nhận nêu tên **cả người chuẩn
   bị lẫn người kiểm chéo**.

---

## 4. Config — phần "chỉnh không cần code" (điểm nhấn với ITer)

Tất cả làm ở **Cửa sổ 1 (An)** trừ bước duyệt ở Cửa sổ 2 (Giang).

### 4.1 Quy tắc & Quy trình DW1

**[An]**
1. Vào **`/sales/rules/process`** (*Sales → Quản lý → Quy trình DW1*): sơ đồ các
   bước đơn hàng/báo giá, và **các công tắc bước AI** (đang khóa — bật bằng cách
   đề xuất phiên bản quy tắc, dưới).
2. Vào **`/sales/rules`** (*Quy tắc*). Bấm **"Đề xuất phiên bản mới: Quy tắc kiểm
   tra đơn hàng"**. Trong hộp thoại: điền **"Số phiên bản mới"** (ví dụ `1.5.99`)
   → **"Xem thay đổi"** (xem khác gì bản đang dùng) → **"Gửi duyệt"**.
3. **Bị từ chối:** An **không tự duyệt** đề xuất của mình được.

**[Cửa sổ 2 — Giang]**
4. Vào **`/approvals`** (trang Duyệt chung). Tìm thẻ yêu cầu `sales.rules`, điền
   **"Nhận xét"** → **"Duyệt"**. Worker áp dụng: bản mới thành bản đang dùng.

> Thông điệp: "Quy tắc là **dữ liệu có phiên bản**, người này đề xuất — người kia
> duyệt, không ai tự đổi luật của chính mình."

### 4.2 Dạy DW một mẫu PO mới (onboard khách mới, không cần deploy)

**[An]**
1. Hộp thư → mở dòng **M43** (mẫu PDF mới, đang "Không đọc được file"). Bấm
   **"Thiết lập mẫu PO"** cạnh tên file.
2. Ở trang thiết lập: gán từng trường với nhãn in trên mẫu (có mô hình thì các
   trường mở sẵn kèm gợi ý; không có thì gán tay). Bấm **"Xem thử"** để DW đọc
   thử theo ánh xạ vừa gán.
3. **"Gửi duyệt"** (nút này khóa cho tới khi "Xem thử" chạy xong).

**[Cửa sổ 2 — Giang]**
4. Vào **`/sales/layouts`** (hoặc từ `/approvals`), bấm **"Duyệt"**, ghi nhận xét.

**[An]**
5. Hộp thư → **"DW xử lý lại"** trên M43: giờ tạo được hồ sơ; mọi giá trị **gắn
   cờ cho người xác nhận** (vì mẫu còn mới).

### 4.3 Prompt & Skill (lướt để cho thấy chiều sâu)

**[An]** Vào **`/sales/rules/prompts`** và **`/sales/rules/skills`**: đây là nơi
tenant xem/sửa **lời hướng dẫn mô hình** (prompt) và **kỹ năng** (skill) theo
phiên bản — thể hiện triết lý "model làm theo chỉ dẫn tenant chỉnh được, thay vì
if/else cứng trong code". Thao tác sửa/đề xuất theo **nút chính trên màn** (tương
tự 4.1: đề xuất → người khác duyệt).

---

## 5. Quản trị & bảo mật (nhanh, nhưng rất "ăn tiền" với IT)

### 5.1 Quản trị người dùng & tách nhiệm — **[Cửa sổ 3 — Chi]**
- **`/admin`**: thẻ *Thành viên* (thêm người, đổi vai, cấp bộ quyền — mục 2b), và
  danh mục *vai → quyền*.
- **`/admin/separation-of-duties`** (*Tách nhiệm*): các **cặp nhiệm vụ không ai
  được giữ cùng lúc**. Muốn khoe quy trình miễn trừ: bấm **"Đề xuất miễn trừ"** +
  ghi lý do → một **quản trị viên thứ hai** phải **"Xác nhận miễn trừ"** thì mới
  có hiệu lực; có cặp ghi **"Luôn áp dụng"** (nền tảng không cho miễn).
- **`/admin/workspaces`**, **`/admin/hierarchy`**, **`/admin/settings`**: workspace,
  tuyến báo cáo, tên công ty/múi giờ/ngôn ngữ.

### 5.2 Ai thấy gì — **cho khán giả thấy phân quyền là thật**
Mở nhanh một cửa sổ ẩn danh, `/dev-login`:
- Đăng nhập **Vũ Thanh Hà** (lãnh đạo) → vào `/sales/overview`: **chỉ số lượng &
  thời gian, không có số tiền**; mọi URL hồ sơ khác → "không có quyền".
- Đăng nhập **Phạm Quốc Bảo** (tenant Beta) → Hộp thư **rỗng**; mở một hồ sơ của
  Alpha bằng link → **404** (không xác nhận hồ sơ tồn tại — cách ly tenant).
- (Tùy chọn) **Ngô Minh Tâm** (IT): menu Sales chỉ có *Quy tắc*; không thấy giá,
  không mở được hồ sơ — IT không phải Sales.

---

## 6. Các màn "hay ho" khác — tour 5 phút

Ở **Cửa sổ 1 (An)** hoặc **2 (Giang)** tùy quyền:
- **`/approvals`** (Duyệt) — hộp duyệt HITL; lượt chạy DW **dừng rồi tiếp** khi có
  quyết định.
- **`/audit`** (Nhật ký kiểm toán) — mọi lượt chạy/quyết định theo thứ tự; việc
  nền ghi dưới tên `system:<lane>`, không mạo danh người.
- **`/sales/activity`** (Hoạt động DW1) — DW tự làm bao nhiêu / chuyển người bao
  nhiêu / vì sao (câu chuyện tự chủ bằng số).
- **`/memory`** (Bộ nhớ), **`/knowledge`** (Tri thức), **`/integrations`** (Tích
  hợp — danh mục công cụ + chính sách) — xem nhanh để thấy bề rộng nền tảng.
- **DW tự xử lý thư**: dừng `make dev`, chạy `make demo-reset` rồi `make dev`
  (không đặt biến tắt làn). Sau ~1 phút DW tự đọc hết hộp thư mà không ai bấm —
  cho thấy chế độ tự động.

---

## 7. (Nâng cao, tùy chọn) Bật AI để DW tự đọc thư/PO

Mặc định AI **tắt** → demo mượt. Muốn khoe AI đọc thư, mô tả hàng, RFQ:
1. Chạy Ollama phục vụ `qwen3.5:9b` và đặt `DW_ONPREM_MODEL_BASE_URL=http://localhost:11434/v1`
   trong `.env`.
2. Đo từng bước bằng `run_evals.py --live onprem --attest …` (xem `demo.md` mục 1).
3. **[An]** đề xuất ở `/sales/rules` một phiên bản bật các bước đã đạt ngưỡng →
   **[Giang]** duyệt. Phiên bản bật bước *chưa đo đạt ngưỡng* bị từ chối (409).

> Nặng RAM/VRAM. Trên máy 16 GB, **đừng** bật AI chung với cả stack trong buổi
> demo đầu; để buổi riêng.

---

## 8. Dọn sau buổi demo

```sh
make demo-reset        # về trạng thái bắt đầu (và xóa quyền rộng đã cấp cho An)
# rồi tắt để nhẹ máy:
docker desktop stop; wsl --shutdown   # tùy môi trường
```

Nhớ: sau `demo-reset`, muốn chạy lại thì **làm lại bước 2b** (cấp quyền rộng cho An).

---

## 9. Hay vấp ở đâu (cho người lần đầu)

- **Bấm "DW xử lý" mà đứng mãi "Đang chờ DW1":** worker chưa chạy, hoặc reader
  chưa lên. Kiểm tra `make dev` còn chạy và image `reader` đã build xong.
- **Thư có file đều "chưa đọc được tệp đính kèm":** xem `.env` có
  `DW_SALES_MALWARE_SCAN=skip` và `reader-gateway` đang chạy (`make dev` không tới
  được clamav nên phải skip).
- **Cấp quyền cho An xong mà An vẫn không thấy giá:** chưa tải lại trang/đăng nhập
  lại ở Cửa sổ 1 để nhận quyền mới.
- **3 cửa sổ bị lẫn phiên:** dùng **Chrome Profiles** (3 profile riêng) thay vì
  ẩn danh.
- **Lỡ `demo-reset` giữa buổi:** mọi hồ sơ về 0 và quyền rộng của An mất — phải
  làm lại bước 2b và chạy lại từ 3.1.
- **Màn quản trị platform (Tenant / Operator / Support) báo lỗi / tải không ra**
  trong khi màn Sales vẫn chạy: role `dw_provisioner` trong volume Postgres
  (được dùng lại giữa các checkout) bị thiếu hoặc sai mật khẩu — chỉ tạo lúc
  khởi tạo volume lần đầu. Sửa một lần, không mất dữ liệu:
  `DW_ADMIN_DATABASE_URL=postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$DW_POSTGRES_HOST_PORT/postgres uv run python scripts/create_provisioner_role.py`
  (lấy biến từ `.env`). Role nằm ở tầng cluster nên còn qua mọi lần
  `make dev`/`infra-up` sau đó.
- **Docker tự tắt giữa buổi (máy 16 GB, chạy full stack + 3 cửa sổ):** cả
  `make dev` chết theo (một tiến trình con tắt là cả cụm tắt). Bật lại Docker
  Desktop, `make infra-up`, rồi `make dev` — data trong volume còn nguyên.

---

## Phụ lục A — bản đồ "cửa sổ → người → màn hình"

| Việc | Cửa sổ | Người | Trang chính |
| --- | --- | --- | --- |
| Đọc thư, làm đơn, định giá, config Sales | 1 (Lái) | An | `/sales/inbox`, `/sales/orders/*`, `/sales/quotes/*`, `/sales/rules*`, `/sales/layouts` |
| Kiểm chéo, duyệt báo giá, duyệt quy tắc | 2 (Duyệt) | Giang | `/sales/orders/*`, `/sales/quotes/*`, `/approvals` |
| Quản trị người dùng, tách nhiệm, workspace | 3 (Admin) | Chi | `/admin`, `/admin/separation-of-duties`, `/admin/workspaces` |
| Khoe phân quyền (lãnh đạo / tenant khác) | ẩn danh tạm | Hà, Bảo | `/sales/overview`, `/sales/inbox` |

## Phụ lục B — vì sao không có 1 account toàn quyền (một dòng cho khán giả)

> "Hệ thống cố tình không cho một người vừa làm vừa tự duyệt, và không cho gộp
> quyền quản trị với quyền xem giá vào một tài khoản — đó là cơ chế chống gian
> lận. Vì vậy demo dùng vài vai, mỗi vai một cửa sổ, đúng như vận hành thật."
