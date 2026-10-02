---
status: Proposed
date: 2026-09-29
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#hướng-đi-sau-phản-biện # hàng Chương Security & Trust riêng
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#101-vị-trí-trong-codebase # hàng configs/tools/bid.*, dw_knowledge, evals
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#104-bảo-mật-và-niềm-tin # hàng Đầu vào không tin cậy, Kiểm chứng
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC01, SEC02, SEC08
---

# Tài liệu tải lên là dữ liệu: lượt mô hình có nội dung tài liệu không gọi được tool gửi ra ngoài

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

E-HSMT, E-HSDT và thư bảo lãnh do khách tải lên.
[Process v0.4](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md) chấp nhận điểm phản biện "Chương
Security & Trust riêng" và viết thành mục 10.4. Hàng "Đầu vào không tin cậy" ở
đó coi các file này là dữ liệu, không là chỉ dẫn. Đây là khuyến nghị của
process v0.4, chưa được kiểm bằng phỏng vấn. Quyết định, theo
[rule-spec](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md) mục 7.4:

- `SEC01`: nội dung tài liệu chỉ vào prompt trong khối được đánh dấu dữ liệu,
  không bao giờ nối vào system prompt. Thực thi ở prompt bundle và eval.
- `SEC02`: lượt mô hình có nội dung tài liệu trong ngữ cảnh chỉ gọi tool đọc
  và tool ghi nội bộ, không gọi tool có side effect ra ngoài. Thực thi ở tool
  executor, bằng policy theo ngữ cảnh.
- `SEC08`: quét mã độc và kiểm định dạng trước khi parse; parser chạy trong
  sandbox không mạng. Thực thi ở worker ingest.

## Hệ quả

- Tool `bid.*` có ba mức (process 10.1): chỉ đọc; ghi nội bộ; gửi ra ngoài,
  luôn cần approval. Việc gửi ra ngoài chỉ xảy ra ở lượt không có nội dung tài
  liệu. "Luôn cần approval" nghĩa là tool spec khai `approval_policy: always`;
  nếu không, ở A3 tool external idempotent tự chạy, ở A4 mọi tool external tự
  chạy (`dw_agent_runtime/autonomy.py:82-83, 127`; ART-10).
- `evals/datasets/bid@1.0.0.json` có ca prompt injection trong file E-HSMT,
  chạy trong CI (process 10.1; 10.4 hàng Kiểm chứng).

## Xung đột và điểm mở

- **`SEC02` chưa có chỗ thực thi (ART-12).** Executor chỉ kiểm scope, approval,
  idempotency (`dw_agent_runtime/executor.py:161, 175, 193`). Tài liệu chưa nói
  thế nào là "có nội dung tài liệu trong ngữ cảnh". Hai đường: cờ theo lượt
  trong executor (sửa nền tảng trên `main`), hoặc tách worker: worker có lượt
  đọc tài liệu dùng toolset không có tool external. Toolset gắn với một phiên
  bản worker, không gắn với node (`dw_agent_runtime/toolsets.py:41`; ART-12;
  xem [ADR 0010 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0010-one-worker-specialised-graphs.md)).
  Cần quyết chỗ thực thi, và lượt sau trong cùng run có bị coi là "có" không.
- **Memory recall được gắn vào system message, trái `SEC01`.**
  `dw_agent_runtime/adapters/recalled_memory.py:17-20` ghi memory được viết từ
  tài liệu khách và được đóng khung là dữ liệu; dòng 114 gắn khối đó vào system
  message. Recall chỉ có khi context truyền `recall` vào `AgentSpec`
  (`adapters/agent_factory.py:139, 185`). Cần quyết: `dw_bid` không nối recall, hay nền tảng đưa recall vào khối
  dữ liệu phía user (ADR nền tảng).
- **Khối dữ liệu không escape.** System prompt tĩnh; biến vào phần user qua
  `template.format`, không escape (`dw_agent_runtime/model/prompts.py:120-121`).
  Prompt mẫu bọc biến trong `<input>`
  (`configs/prompts/platform/untrusted_demo@1.0.0.yaml:12-14`). Grader chỉ
  render prompt rồi kiểm vị trí marker, không gọi mô hình
  (`dw_evals/graders.py:63-89`). Cần quyết cách xử lý nội dung có sẵn thẻ đóng
  khối, và eval có ca chạy mô hình thật không.
- **Parser hiện tại trái `SEC08` (MODEL-14).** Tài liệu và ảnh được gửi nguyên
  file (base64) tới mô hình qua gateway (`GatewayFileParser`), âm thanh tới
  Deepgram, nên parser cần mạng
  (`dw_knowledge/adapters/api_parsers.py:6-12, 28, 134`). Sandbox không mạng
  hiện chỉ có docgen, trên mạng riêng `dw-sandbox`; worker nằm trên `dw-edge`
  (`infra/compose/docker-compose.yml:24-27, 442, 546`). Cần quyết có dựng parser
  cục bộ trong sandbox không mạng không, tức đảo việc đã bỏ parser cục bộ; liên
  quan [ADR 0006](0006-model-routing-by-data-classification.md).
- **Chưa có quét mã độc, kiểm định dạng.** Tìm `clamav|malware|antivirus`
  trong `packages`, `apps`, `infra`, `configs`, `scripts`: không có. Ingest chọn
  tuyến theo đuôi file (`configs/policies/attachment_ingest@1.1.0.yaml:7-9`).
  Cần quyết công cụ quét, chỗ chạy, và xử lý file bị từ chối.
- **Tra luật qua web (DOCS-53).** `process.md:668` cho `legal` "đi web như
  DW01": tool đọc mà vẫn gửi câu truy vấn ra ngoài, trong khi `SEC02` cho phép
  mọi tool đọc. Cần quyết tìm kiếm web có tính là tool gửi ra ngoài không.

Các mã như `TEN-02`, `DOCS-15` là mục trong [bản đối chiếu tài liệu với repo ngày 29/9/2026](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/audit-2026-09-29.md).
