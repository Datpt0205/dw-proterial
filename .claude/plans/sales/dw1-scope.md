# DW1 — tính năng nào theo quy trình Proterial, tính năng nào mình tự đề xuất

Lập ngày 2026-10-19, theo yêu cầu của Đạt. Phạm vi là DW1 (Đơn hàng & Báo giá,
WIV-03-012 và WIV-03-023); DW2 chưa làm. Chín agent đối chiếu, hai agent phản
biện kiểm lại từng trích dẫn. Số đo AI ở mục 4 là lần chạy lại cùng ngày.

**Nguồn quy trình**

- **KS:** phiếu "Form khảo sát công việc - SALE" mà Proterial gửi. PDF nằm
  ngoài git, vì repo public. KS:n là dòng n trong bản trích văn bản của phiếu.
- **spec.md:** đặc tả DW1; các bước O1–O11 (đơn hàng) và Q1–Q12 (báo giá)
  được rút ra từ phiếu.
- **Đề xuất FPT:** deck gửi Proterial; chỉ dùng để xem FPT đã hứa phạm vi gì.

**Lớp phân loại**

- **R:** quy trình Proterial yêu cầu.
- **S:** quy tắc nền tảng hoặc bảo mật bắt buộc (CLAUDE.md); Proterial không yêu
  cầu, nhưng không bỏ được.
- **E:** mình (FPT, agent hoặc Đạt) tự đề xuất thêm.

## Tóm tắt

- 58 tính năng: 24 R, 17 S, 17 E.
- Trong 24 tính năng R:
    - 7 khớp chuẩn;
    - 12 khớp một phần, phần lớn vì đang chạy trên dữ liệu hoặc mẫu MOCK;
    - 3 lệch: F05 và F06 đổi thứ tự O6/O7, F49 lệch phạm vi;
    - 2 chưa làm: F56, F58.
- Bước trong phạm vi DW1 chưa làm:
    - thư thật M365 và cổng khách hàng (O1);
    - ghi vào Bravo (O3);
    - ký điện tử (Q9);
    - các bước kiểm soát xuất khẩu WIV-03-032 (mới có cảnh báo NOC/ESF);
    - tạo khách mới WIV-03-031.
- Hoãn sang DW2: O5, O11 và CDO (WIV-03-022).
- DW1 không dùng retrieval. bge-m3 và bge-reranker-v2-m3 chỉ phục vụ phần
  knowledge của nền tảng.

## R — theo quy trình Proterial (24)

| Tính năng                                           | Bước           | Khớp         | Ghi chú                                                                    |
| --------------------------------------------------- | -------------- | ------------ | -------------------------------------------------------------------------- |
| F02 Nhận PO, phân loại thư                          | O1             | Một phần     | Hộp thư MOCK, chưa có cổng KH                                              |
| F03 Đọc PO Excel/PDF có chữ, anchor, độ phủ         | O3             | Một phần     | Anchor và câu khai độ phủ là thiết kế của DW1 (ADR 0009)                   |
| F04 Chuyển mã sang mã PRV                           | O2             | Đúng         | Convert list MOCK hoặc nhập file (41)                                      |
| F05 Kiểm PO với báo giá, LT ngắn, khách tạm, NOC    | O6, O4         | Lệch thứ tự  | Kiểm trước khi nhập Bravo; cảnh báo LT ngắn gửi Sales, khảo sát nói gửi PC |
| F06 PIC tự kiểm, "Chuẩn bị xong"                    | O7             | Lệch thứ tự  | Cùng lý do với F05                                                         |
| F08 Sửa trường không chắc chắn                      | O3             | Đúng         | 15                                                                         |
| F09 Yêu cầu khách sửa PO; PO sửa thay bản cũ        | O8             | Đúng         |                                                                            |
| F10 Gợi ý ngày giao theo LT chuẩn                   | O4             | Một phần     | Bản tạm; Proterial định làm trên Bravo                                     |
| F11 File nhập Bravo, "Đã nhập Bravo"                | O3             | Một phần     | Không ghi vào Bravo; mẫu MOCK                                              |
| F12 Kiểm chéo bởi Sales khác                        | O9             | Đúng         | Đề xuất FPT hứa bỏ bước này; spec giữ                                      |
| F13 Xác nhận PO, nêu tên hai người và ngày giao     | O10            | Đúng         |                                                                            |
| F17 Nhận RFQ, anchor, hạn báo giá                   | Q1             | Một phần     | MOCK                                                                       |
| F18 Phiếu YCBG, nháp gửi Design                     | Q2–Q3          | Một phần     | Mẫu MOCK; chỉ soạn nháp                                                    |
| F19 Trả lời của Design khớp theo số YCBG            | Q4             | Một phần     | Hộp thư Design MOCK                                                        |
| F20 Từ chối báo giá có lý do; trao đổi spec         | Q5–Q6          | Đúng         |                                                                            |
| F21 Căn cứ giá; Sales quyết giá                     | Q7             | Đúng         | DW1 không đề xuất giá                                                      |
| F22 Tài liệu báo giá xlsx/PDF                       | Q8             | Một phần     | Mẫu MOCK                                                                   |
| F23 Trưởng phòng hoặc người thay duyệt              | Q9             | Một phần     | Bản cứng vẫn là bản duyệt chính thức; chưa ký điện tử                      |
| F24 Nháp gửi báo giá; dòng master list              | Q10–Q11        | Một phần     | Q11 trên MOCK                                                              |
| F25 Rà soát mã 12 tháng không có đơn                | Q12            | Một phần     | MOCK                                                                       |
| F45 Model đọc RFQ                                   | Q1→Q2          | Một phần     | Proterial đề xuất dùng AI ở bước này (KS: Copilot)                         |
| F49 Nháp chuyển PC/QA                               | O5             | Lệch phạm vi | O5 thuộc DW2; hàng mẫu khảo sát gửi Design, không gửi PC/QA                |
| F56 Việc chờ Proterial (NOEC, M365, ma trận, Bravo) | WIV-03-032, O1 | Chưa làm     | Ticket 12                                                                  |
| F58 Phần DW2 của WIV-03-012 (O5, O11)               | O5, O11        | Hoãn DW2     |                                                                            |

## S — bắt buộc theo nền tảng hoặc bảo mật (17)

| Tính năng                                                      | Ticket        |
| -------------------------------------------------------------- | ------------- |
| F01 Dữ liệu và hộp thư MOCK sau port thật                      | 01            |
| F07 Xem nguồn; phải mở nguồn mới được chuẩn bị/kiểm chéo       | 05, 08, 29    |
| F26 File và nháp render từ hồ sơ, có phiên bản và sha256       | 06            |
| F27 Lưu trữ Sales: RLS FORCE, CHECK maker/checker, offboarding | 04, 05, 10    |
| F28 API theo scope, case_version, Idempotency-Key, ẩn số tiền  | 05, 11        |
| F29 Vai trò và persona                                         | 11, 04, 16    |
| F30 DW1 chạy trên agent runtime; quyết định là approval có dấu | 10            |
| F31 Nút dừng: PIC dừng, chỉ trưởng phòng cho chạy lại          | 05            |
| F36 "DW xử lý" bất đồng bộ qua worker                          | 25            |
| F37 Quét mã độc (ClamAV) trước khi đọc file                    | 25            |
| F38 Đọc file trong sandbox `reader`                            | 25            |
| F41 FPT hỗ trợ đọc khi khách cấp quyền, ẩn số tiền             | 22            |
| F42 Không lộ giá, tên khách, nội dung thư vào log/trace        | 23            |
| F43 Chặn dữ liệu khách vào repo public (deny-list)             | 26            |
| F50 Quy tắc và mẫu riêng của tenant, đề xuất và duyệt          | 19, 36–38     |
| F54 Giao diện portal Sales (antd v6)                           | 07, 08, 39    |
| F55 Eval, rà soát bảo mật, demo walk                           | 09, 18, 28–33 |

## E — mình tự đề xuất thêm (17)

| Tính năng                               | Ai đề xuất               | Ghi chú                         |
| --------------------------------------- | ------------------------ | ------------------------------- |
| F14 Đóng hồ sơ có lý do                 | Bản sửa sau rà soát      | Hỗ trợ O1, O8                   |
| F15 Một dòng PO nhiều lịch giao         | Agent                    | Chưa kiểm được: chưa có PO thật |
| F16 Ô ngày trống; .xlsx cùng bản in PDF | Agent                    | Hỗ trợ O3                       |
| F32 "Việc cần làm"                      | Theo lời hứa FPT         |                                 |
| F33 Tổng quan, KPI, đếm ngầm A3         | Theo lời hứa FPT         |                                 |
| F34 Trưởng phòng giao lại hồ sơ         | Spec                     | Khảo sát không có bước giao     |
| F35 Mailbox lane tự xử lý thư           | FPT ("trực 24/7")        |                                 |
| F39 LibreOffice .xls/.doc, OCR          | Agent                    | Chưa đo                         |
| F40 Font TCVN3/VNI                      | Agent                    | Còn hai lỗ hổng                 |
| F44 Model đọc mô tả hàng                | Agent                    | Hỗ trợ O2                       |
| F46 Khai báo layout PO mới              | Agent                    |                                 |
| F47 Model phân loại thư                 | Agent                    |                                 |
| F48 Gắn thư trả lời, đề xuất bước tiếp  | Agent                    |                                 |
| F51 Form sửa quy tắc (40)               | Đạt, 2026-10-18          | Chưa xem trang render           |
| F52 Nhập dữ liệu gốc từ file (41)       | Đạt, 2026-10-18          |                                 |
| F53 Nhắc việc, bản tin 07:30 (42)       | Theo lời hứa FPT         |                                 |
| F57 Tự xác nhận trong ngưỡng (A3)       | Lời hứa FPT "sau 4 tuần" | Chưa làm; mới có đếm ngầm       |

## Bước Proterial không có trong spec

- WIV-03-005: hàng air bất thường.
- PRGM code.
- WIV-03-006: hàng mẫu.
- WIV-03-027: catalogue.
- WIV-03-011: khiếu nại. F49 chỉ soạn bản chuyển giao.
- Forecast: Proterial đang tự làm với IT.
- Việc hành chính, audit, thăm khách.

## AI trên máy (Qwen3.5-9B, bge-m3, bge-reranker-v2-m3)

**Các bước model của DW1**

- Sáu bước model của DW1 (ticket 28–33) chỉ gọi route `structured_extraction`
  của profile `onprem`.
- Mọi phép kiểm, mọi con số, ngày, giá và văn bản gửi khách do code làm. Người
  duyệt mọi giá trị model đọc ra.
- Sáu công tắc `model_assist` đều tắt ở tầng platform. Chỉ tenant demo bật.

**Đo lại ngày 2026-10-19**

Chạy trên Ollama 0.40.4 cài trên máy, `qwen3.5-9b-dw` Q4_K_M, num_ctx 8192,
thinking tắt, GTX 1080 Max-Q 8 GB, dữ liệu mock. Cả sáu dataset đều PASS phần
bảo mật.

| Bước                        | Kết quả                                    | Bar          | p95    |
| --------------------------- | ------------------------------------------ | ------------ | ------ |
| t28 mô tả hàng → thuộc tính | VI/EN 71,1%; JA 50%; 0 ứng viên đơn lẻ sai | 70%          | —      |
| t29 đọc RFQ                 | 94,9%; **1 giá trị bịa**                   | 85%          | 23,0 s |
| t30 layout PO               | 97,7%; 0 giá trị sai được chấp nhận        | 90%          | 11,8 s |
| t31 phân loại thư           | 89,8%; bảng từ khoá 27,3%                  | 90%: **hụt** | 4,2 s  |
| t32 thư trả lời             | 97,8%                                      | đạt          | 4,9 s  |
| t33 hand-off                | 94,5%; 0 trường bịa                        | 85%          | 7,2 s  |

Chạy lại t31, t30 và t33 trên Ollama 0.34.4 trong container on-prem được
89,8%, 97,7% và 98,6%, nên bản ghim trong compose cho cùng kết quả.

**Embedding và rerank chạy local.** bge-m3 cho vector 1024 chiều và xếp đúng
câu trả lời tiếng Việt, tiếng Anh và tiếng Nhật. bge-reranker-v2-m3 xếp câu đúng
lên đầu, mất 1,5 s trên CPU. DW1 chưa dùng hai model này.

**Có thể giao thêm cho AI**, theo thứ tự đáng làm:

0. Nạp convert list từ lịch sử bán của Bravo. Không cần AI, và đây cũng là
   nhãn đúng miễn phí cho t28.
1. Map mã PRV (O2) bằng retrieval:
    - bge-m3 và reranker tìm ứng viên trong danh mục của tenant; Sales chọn.
    - Đây là chỗ hai model local có ích cho DW1.
    - Cần một Protocol do DW1 tự khai, theo luật "consumer declares".
2. Đọc thư trả lời tự do của Design (Q4).
3. Tóm tắt có trích dẫn một luồng trao đổi spec (Q6).
4. Nhận diện khiếu nại (WIV-03-011). Phải chờ quyết phạm vi.
5. Đọc ngày trả lời của PC (O4/O5). Nghiêng về DW2.

Hỏi đáp trên hồ sơ bị chặn: profile `onprem` không có route `chat`.

**Luôn để người làm:** giá, mọi bước duyệt, ngày giao, kiểm soát xuất khẩu, mọi
văn bản gửi khách.

## Câu hỏi cho Proterial

1. Gửi văn bản WIV-03-012 và WIV-03-023, kèm PO và RFQ mẫu thật.
2. Có chấp nhận kiểm PO với báo giá trước khi nhập Bravo (đổi thứ tự O6/O7) không?
3. Giữ hay bỏ bước kiểm chéo O9?
4. Cảnh báo LT ngắn gửi PC hay gửi Sales?
5. Đổi lịch giao, khiếu nại, hàng mẫu nằm ở DW1 hay DW2? Hàng mẫu gửi Design hay PC/QA?
6. Có cho AI chạy trên tài liệu thật, trên máy chủ đặt tại nhà máy không? Máy
   chủ có GPU loại nào?
7. PO và RFQ thật có mô tả hàng tiếng Nhật không?
8. Có cần ký điện tử cho Q9 không?
9. WIV-03-032 (screen sản phẩm, denial list, NOEC, ESF) và WIV-03-031 (tạo khách
   mới) có thuộc DW1 không?

## Cho Đạt

- **DW2 là gì?** Hai deck FPT ghi khác nhau: một deck ghi "Giao hàng & CDO",
  deck kia và `infra/onprem/README.md` ghi "Mua hàng".
- **Duyệt hoặc sửa bar của t29–t33.** Các bar này do agent đề xuất. t31 hụt 0,2
  điểm ở lần đo này.
- **Chặn egress ở tầng mạng?** api và worker vẫn nằm trên `dw-edge` kể cả ở
  on-prem. Hiện "không gọi ra ngoài" chỉ được giữ bằng cấu hình trong ứng dụng.
