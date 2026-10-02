---
status: Proposed
date: 2026-09-30
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#21-dữ-kiện-có-neo-nguồn # SourceAnchor
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC14
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#41-vòng-đời-bằng-chứng
---

# Parser trả kết quả theo trang, có tọa độ; neo nguồn mang vùng trên ảnh trang

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

Chỉ dữ kiện đã có người xác minh mới cho PASS (EV01), và D15 khuyên xác nhận từng
dữ kiện. Người xác minh chỉ bắt được lỗi OCR (2.500.000.000 đọc thành
2.000.000.000) khi nhìn thấy đúng chỗ đó trên ảnh trang gốc. Hôm nay thì không
được. `ParsedDocument` của nền tảng chỉ có văn bản, tiêu đề, số trang và cảnh báo
(`packages/python/dw_knowledge/src/dw_knowledge/ports.py:73-83`): không có văn
bản theo trang, không có tọa độ. Parser gửi nguyên tệp cho mô hình trong một lời
gọi (`packages/python/dw_knowledge/src/dw_knowledge/adapters/api_parsers.py:30-32, 132-160`).
Neo nguồn của rule-spec 2.1 chỉ có offset trên văn bản do parser trả về, nên
không tô được lên ảnh. Một PDF có lớp chữ ẩn, hoặc lớp chữ lệch với ảnh, cũng lọt
qua mà không ai thấy: đó vừa là đường đưa số sai vào, vừa là đường chèn chỉ dẫn
cho mô hình.

Đạt chốt `[Đạt chốt]` là người xác minh phải nhìn được ảnh trang gốc. Cách làm
dưới đây là đề xuất `[Đề xuất 30/9]`.

**Quyết định.**

1. **Parser trả kết quả theo trang.** Với mỗi trang: số trang, ảnh trang đã dựng
   (ở object storage, đường dẫn mang tenant và workspace; lưu lâu dài hay dựng lại
   khi cần là điểm mở 5), các khối chữ kèm khung tọa độ trên trang, nguồn của chữ
   (lớp chữ có sẵn hay OCR), độ tin cậy OCR, và cờ: chữ ẩn (có trong lớp chữ nhưng
   không hiện khi dựng ảnh), lớp chữ lệch ảnh, OCR kém. Mỗi trang có trạng thái kiểm
   cờ ba giá trị: đã kiểm sạch, có cờ, chưa kiểm. Với tệp Office, chữ lấy từ đúng
   bản đã dựng thành ảnh (PDF sau chuyển đổi,
   [ADR nền tảng 0010](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/adr/0010-document-intake-at-real-size-and-format.md)); nếu không,
   parser phải gắn cờ tường minh cho đoạn ẩn, dòng, cột, sheet ẩn và chữ cùng màu
   nền.
2. **Neo nguồn mang vùng.** `SourceAnchor` có thêm các khung trên ảnh trang; mỗi
   khung gồm trang, x, y, w, h theo tỷ lệ 0–1 của trang, và hash ảnh trang
   (`PageBox`, rule-spec 2.1). Neo mang cả hash bản gốc lẫn hash bản dẫn xuất (sau
   chuyển đổi). `start_offset`, `end_offset`, `quote` thành tùy chọn, với bất biến:
   có ít nhất một trong (quote cộng offset), khung, `cell_ref`. Có chữ thì
   `locate_quote` tìm câu trong văn bản của đúng trang đó, rồi neo giữ cả offset
   lẫn khung. Neo chỉ có vùng (trang scan chưa có chữ, vùng khoanh tay ở
   [ADR 0019 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0019-near-deadline-path-without-model.md))
   không chứng minh được giá trị: neo phải ghi người chứng thực (ai, lúc nào), và dữ
   kiện phải được một người khác xác minh trên ảnh.
3. **Người xác minh thấy ảnh.** Màn xác minh hiện giá trị máy trích cạnh vùng ảnh
   trang đã tô. Server chỉ nhận xác nhận khi đã phục vụ vùng ảnh trang của neo cho
   chính user xác nhận, trong cùng phiên, trước lúc xác nhận (EV08; neo theo ô và
   lối tối thiểu của ADR 0019 có biến thể riêng ở đó). Server không
   biết ảnh có hiện trên màn hình hay không, chỉ biết đã phục vụ ảnh cho ai; cách
   làm giống DR03 cho khối `ai_new`.
4. **Cờ an ninh chặn dữ kiện.** Dữ kiện lấy từ vùng có cờ chữ ẩn hoặc lớp chữ lệch
   ảnh ở lại `UNKNOWN` cho tới khi người xác nhận trên ảnh; tài liệu có cờ được
   đánh dấu trong báo cáo rà soát (SEC14). Trang "chưa kiểm" xử lý như có cờ: parser
   không trả cờ không có nghĩa là trang sạch. Có test: tệp có chữ ẩn mà parser không
   trả cờ thì dữ kiện vẫn `UNKNOWN`.
5. **Ảnh trang là dữ liệu của tài liệu gốc.** Ảnh trang và vùng cắt thừa hưởng
   phân loại và nhóm giá của tài liệu gốc. Ảnh luôn đọc qua API, kiểm vai ở mỗi lần
   đọc, cùng khuôn với `apps/api/src/dw_api/routes/v1/feedback.py:8-10`; không dùng
   link ký sẵn. Ở dw_bid, trang của tài liệu nhóm giá chỉ `bid_pricing`, `bid_owner`
   mở được (Q05,
   [ADR 0007 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0007-bid-price-visible-to-pricing-and-owner-only.md)),
   và bộ lọc giá của ngữ cảnh hỗ trợ
   ([ADR nền tảng 0008](0008-customer-granted-support-access.md)) áp cả ở đây. Xóa
   tenant và EV07 xóa luôn ảnh trang. Có test âm: `bid_lead` và ngữ cảnh hỗ trợ
   không mở được ảnh trang của bảng giá.
6. **Neo mất hiệu lực theo trang.** Ngoài đổi tệp, đổi phiên bản parser, đổi bộ
   chuyển đổi hay chạy lại một trang cũng vô hiệu neo của trang đó (EV07 mở rộng).

## Phương án đã cân nhắc

- **Giữ văn bản thuần, mở PDF bằng pdf.js và tô theo tìm chữ.** Loại: với bản
  scan thì không có lớp chữ để tô; với PDF có lớp chữ thì tô lên lớp chữ, không
  phải lên thứ người ta nhìn thấy.
- **Cho mô hình trả tọa độ.** Loại: mô hình không đáng tin về tọa độ, và trái
  nguyên tắc "mô hình đọc, mã quyết".

## Hệ quả

- `DocumentParserPort` đổi hình dạng đầu ra; đây là việc của nền tảng, làm trên
  `main`. Parser mà D10 chọn phải trả được bố cục và tọa độ (điểm mở 1). Dựng lại
  parser cục bộ là đảo quyết định đã bỏ nó
  ([ADR nền tảng 0006](0006-model-routing-by-data-classification.md),
  [0007](0007-document-content-turns-cannot-call-outbound-tools.md)).
- Ảnh trang tốn chỗ lưu và theo retention của tài liệu; con số ước ở điểm mở 5.
- Lối làm tay sát giờ
  ([ADR 0019 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0019-near-deadline-path-without-model.md))
  dựa vào ảnh trang và văn bản theo trang, nên chỉ chạy được khi không có mô hình
  nếu việc dựng ảnh trang và tách chữ chạy cục bộ. Lối tối thiểu khi chưa có nằm ở
  ADR đó.
- Rule-spec: bản ghi neo ở mục 2.1; EV07 mở rộng và EV08 mới ở mục 7.1; SEC14 viết
  lại theo quyết định 1 và 4.
- Màn SourceView trong thiết kế đổi từ tô trên văn bản sang tô trên ảnh trang
  ([đề bài giao diện](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/ui-brief-2026-09-30.md)).

## Xung đột và điểm mở

1. **Chọn parser** (D10). ADR này cần D10 chọn (b), hoặc (d) với OCR cục bộ trả
   khung: OCR qua gateway là mô hình đọc, không cho khung đáng tin
   ([Phương án đã cân nhắc](#phương-án-đã-cân-nhắc)), nên đúng những trang scan cần
   xác minh nhất sẽ không tô được. Còn phải đo parser nào cho tọa độ ổn định trên
   bản scan tiếng Việt, chạy cục bộ trong sandbox không mạng.
2. **Bảng biểu** (BOQ trong PDF): khung theo ô hay theo dòng. Với tệp Excel thì neo
   theo ô, xem [ADR 0020 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0020-numeric-files-go-through-code.md).
3. **Khung nằm ở đâu** (D11). Quyết định 2 đề xuất để khung trong `SourceAnchor`;
   D11 (a) đề xuất một loại neo `RegionAnchor` riêng (trang, khung, người chứng
   thực, thời điểm). Neo khoanh tay (ADR 0019 của context) và neo theo ô (ADR 0020
   của context) không có quote hay offset, nên câu trả lời của D11 quyết luôn bất
   biến ở quyết định 2.
4. **Chỗ đặt `locate_quote`** (D12): trong dw_bid hay trong một package nền tảng.
   Việc tìm câu theo trang ở quyết định 2 đi theo chỗ đó.
5. **Lưu ảnh hay dựng lại khi cần.** Ước 200–400 trang mỗi E-HSMT (ADR nền tảng
   0010), khoảng 0,1–0,5 MB mỗi ảnh trang (chưa đo), tức 20–200 MB mỗi E-HSMT, chưa
   tính E-HSDT và kho năng lực. Bộ đã nộp giữ tối thiểu 5 năm
   ([ADR 0014 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0014-retention-submitted-bids-five-years.md)).
   Cân nhắc dựng ảnh khi cần từ tệp gốc, cộng cache có hạn, thay vì lưu 5 năm; khi
   đó ảnh dựng lại phải ra đúng hash ảnh trang mà neo giữ.
