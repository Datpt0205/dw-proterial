---
status: Proposed
date: 2026-09-30
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#24-khách-cần-chuẩn-bị-gì
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#104-bảo-mật-và-niềm-tin # hàng Tài liệu đầu vào
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#82-mốc-và-con-số-sản-phẩm-phải-tính # 9 ngày chuẩn bị
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC08
---

# Nhận tài liệu ở kích thước, định dạng và chất lượng thật

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

E-HSMT xây lắp thật dài 200–400 trang, nhiều trang scan, kèm bản vẽ và tệp nén.
Kho năng lực của nhà thầu có tệp `.doc`, `.xls` đời cũ, ảnh `.tif`, tệp `.rar`, văn
bản gõ bằng font TCVN3 hoặc VNI. Gói không quá 20 tỷ có thể chỉ có tối thiểu 9 ngày
chuẩn bị (mục 8.2). Nền tảng hôm nay:

- giới hạn 50 MB và đọc cả tệp vào bộ nhớ API
  (`apps/api/src/dw_api/routes/v1/knowledge.py:29, 128`);
- parser gửi nguyên tệp cho mô hình trong một lời gọi, chờ tối đa 300 giây
  (`packages/python/dw_knowledge/src/dw_knowledge/adapters/api_parsers.py:30-32, 132-160`);
- chỉ nhận `.pdf`, `.docx`, `.xlsx`, `.pptx`, vài loại ảnh, văn bản thuần và âm
  thanh (`configs/policies/attachment_ingest@1.1.0.yaml:15-22`);
- không kiểm chất lượng ảnh trước khi trích, nên ảnh mờ thành dữ kiện sai rồi mới
  phải đính chính; không có tiến độ theo trang, không chạy lại được từng trang.

Đạt chốt `[Đạt chốt]` là sản phẩm phải nhận được tài liệu thật. Cách làm dưới đây
là đề xuất `[Đề xuất 30/9]`, của nền tảng vì mọi context nhận tài liệu đều cần.

**Quyết định.**

1. **Tải lên theo luồng, không nạp cả tệp vào bộ nhớ API.** API nhận tệp theo luồng
   (stream) và ghi vào object storage theo từng phần (multipart). Mức phơi ra giữ
   nguyên: storage vẫn không mở cho trình duyệt
   (`apps/api/src/dw_api/routes/v1/feedback.py:8-10`). Chỉ mở storage cho trình
   duyệt khi đo thấy cách này không đủ ([Phương án đã cân nhắc](#phương-án-đã-cân-nhắc)).
   Đường nào cũng giữ các điều sau:
    - server sinh khóa object từ AccessContext (`<tenant>/<workspace>/uploads/<id>`),
      không nhận khóa từ client;
    - giới hạn kích thước là tham số của policy, có phiên bản, kiểm cả khi nhận lẫn
      khi hoàn tất; vượt thì xóa và từ chối;
    - tệp nằm ở vùng cách ly tới khi quét mã độc xong (quyết định 6);
    - không tin content-type do trình duyệt khai;
    - lượt tải bỏ dở được dọn theo lifecycle của storage;
    - có test âm: khóa ngoài tiền tố tenant bị từ chối.
2. **Nhận định dạng thật**: `.pdf`, `.docx`, `.xlsx`, `.doc`, `.xls`, `.tif`, ảnh, `.zip`,
   `.rar`, `.7z`. Tệp có mật khẩu bị từ chối kèm lời nhắn rõ ràng.
    - **Tệp Office đời cũ** được chuyển sang định dạng mới hoặc PDF trong một sandbox
      dùng một lần cho mỗi tệp: giới hạn CPU, bộ nhớ, thời gian; không mạng; không
      chạy macro. Tệp dẫn xuất có hash riêng và ghi phiên bản bộ chuyển đổi; neo mang
      cả hai hash ([ADR nền tảng 0009](0009-parser-page-output-with-coordinates.md)).
      Đổi phiên bản bộ chuyển đổi coi như đổi tệp theo EV07.
    - **Tệp nén** được giải trong sandbox, có giới hạn độ sâu, số tệp, tổng dung
      lượng và tỷ lệ nén để chặn tệp nén độc. Entry được liệt kê bằng thư viện rồi
      ghi theo khóa object do server sinh; tên gốc chỉ giữ làm metadata. Bỏ symlink,
      hardlink. Không dùng lệnh giải nén ghi thẳng theo tên có trong tệp nén (unrar
      từng có lỗi path traversal, CVE-2022-30333). Mỗi tệp bên trong thành một tài
      liệu và được quét mã độc lại; tệp con có mật khẩu thì từ chối. Có test
      zip-slip, symlink và tên tệp mã CP437.
3. **Chuyển mã tiếng Việt cũ.** Phát hiện TCVN3, VNI và chuyển sang Unicode trước
   khi trích; không chắc thì gắn cờ, không đoán. Tệp Office phát hiện theo tên font
   (`.VnTime`, `VNI-Times`). PDF thì so chữ đã chuyển mã với OCR của ảnh trang, lệch
   thì gắn cờ. Dữ kiện lấy từ đoạn bị gắn cờ ở lại `UNKNOWN` tới khi người xác nhận
   trên ảnh trang, cùng cơ chế với SEC14.
4. **Xử lý theo trang.** Tách trang, xử lý song song, mỗi trang có trạng thái riêng,
   chạy lại được từng trang, và người dùng thấy tiến độ. Chạy lại một trang không đè
   dữ kiện đã xác minh hay đã đính chính: nó sinh bản đề xuất mới và báo khác biệt.
5. **Kiểm chất lượng trước khi trích.** Độ phân giải, mờ, nghiêng, tương phản. Tài
   liệu của chính khách có trang kém thì báo "ảnh kém, chụp lại" ngay, trước khi
   thành dữ kiện. Tài liệu của bên ngoài (E-HSMT, thư bảo lãnh) không chụp lại được:
   trang kém vẫn được trích, gắn cờ, dữ kiện ở `UNKNOWN`, và mở lối làm tay
   ([ADR 0019 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0019-near-deadline-path-without-model.md)).
6. **Quét mã độc trước khi làm gì khác** (SEC08), trong sandbox không mạng. Chữ ký
   mã độc đến qua ảnh container có ký, cập nhật định kỳ.

## Phương án đã cân nhắc

- **Giữ giới hạn 50 MB và cho mô hình đọc nguyên tệp** (phương án (a) của D10).
  Loại: timeout, tốn tiền, và gửi nguyên tệp ra ngoài trước khi có nhãn.
- **Trình duyệt tải thẳng lên object storage.** Để dành: đây là đổi mức phơi ra, vì
  hôm nay storage không mở cho trình duyệt. Chỉ dùng khi đo thấy tải theo luồng qua
  API không đủ, và phải qua reviewing-deployment-security: khóa object do server
  sinh có tiền tố tenant/workspace, POST policy có `content-length-range` (PUT ký
  sẵn không chặn được kích thước). Các điều chung ở quyết định 1 vẫn áp.
- **Bắt khách tự chuyển định dạng.** Loại: công ty xây lắp nhỏ không làm được, và
  đó là lý do họ bỏ ngay tuần đầu.

## Hệ quả

- Luồng nhận tài liệu của nền tảng đổi (tải lên, sandbox chuyển đổi, parser theo
  trang theo [ADR nền tảng 0009](0009-parser-page-output-with-coordinates.md)). Làm
  trên `main`.
- Sandbox cần công cụ chuyển đổi và giải nén; công cụ nào, giấy phép ra sao là việc
  phải kiểm (D57).
- Giới hạn nhận vào (policy nền tảng, ADR này) và giới hạn nộp lên Hệ thống (tham
  số pack của quy tắc B06, theo hướng dẫn Hệ thống) là hai tham số, hai chủ. Nền
  tảng nhận `.rar`, `.doc` để đọc không có nghĩa là được nộp chúng. B06 không bao
  giờ đọc policy nhận vào.
- Quy tắc SEC08 của rule-spec mở rộng theo quyết định 2, 3 và 6.
- Màn tải lên có tiến độ theo trang, cảnh báo chất lượng, và danh sách tệp bị từ
  chối kèm lý do ([đề bài giao diện](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/ui-brief-2026-09-30.md)).

## Xung đột và điểm mở

1. **Giới hạn và công cụ** (D57): kích thước tối đa mỗi tệp và mỗi lần tải; công cụ
   giải `.rar` và chuyển Office đời cũ có giấy phép dùng được không `[Kiểm văn bản
gốc]`; mục tiêu thời gian bóc một E-HSMT 300 trang.
2. **Hàng đợi chưa biết hạn chót.** 75 tệp onboarding của một khách có thể chặn
   E-HSMT của gói đóng thầu sáng mai. Cần quyết: ưu tiên theo hạn, công bằng giữa
   tenant, và parser chạy ở dịch vụ riêng. Đây là mục PILOT-21 trong danh sách
   khoảng trống production, chưa quyết.
3. **Chọn parser** (D10). Xử lý theo trang và việc bỏ gửi nguyên tệp cho mô hình
   phụ thuộc parser mà D10 chọn;
   [ADR nền tảng 0009](0009-parser-page-output-with-coordinates.md) cùng phụ thuộc
   đó.
