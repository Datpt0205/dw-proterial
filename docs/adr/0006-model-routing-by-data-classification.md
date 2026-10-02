---
status: Proposed
date: 2026-09-29
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#hướng-đi-sau-phản-biện # hàng Model gateway
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#103-định-tuyến-mô-hình-theo-phân-loại-dữ-liệu
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#104-bảo-mật-và-niềm-tin # Dữ liệu cá nhân, Không huấn luyện, Quan sát
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#11-quyết-định-thiết-kế-đã-chốt # Q15
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC03, SEC04, SEC11
---

# Model gateway định tuyến theo nhãn phân loại dữ liệu

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

Dữ liệu sản phẩm E-HSDT xử lý gồm cả văn bản công khai lẫn giá dự thầu, lý lịch
nhân sự và số CCCD. [Process v0.4](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md) mục 10.3 chốt:
graph không gọi thẳng nhà cung cấp mô hình. Mọi lời gọi đi qua model gateway
của nền tảng và mang nhãn phân loại cao nhất của dữ liệu trong ngữ cảnh
(`SEC03`). Gateway chọn đích theo bảng định tuyến và chính sách mô hình của
từng tenant (`TenantOverlay` trên model profile). Đây là khuyến nghị của
process v0.4, chưa được kiểm bằng phỏng vấn.

| Nhãn           | Ví dụ dữ liệu                                                 | Đích mặc định                                                                           |
| -------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `public`       | E-HSMT, E-TBMT công khai, văn bản luật                        | Mô hình cloud qua gateway                                                               |
| `internal`     | Hồ sơ năng lực không có dữ liệu cá nhân, thuyết minh kỹ thuật | Endpoint cloud có cam kết không huấn luyện, vùng dữ liệu được duyệt                     |
| `confidential` | Giá dự thầu, đơn giá, BCTC chưa công bố, lý lịch nhân sự      | Mô hình đặt tại Việt Nam, endpoint riêng, hoặc mô hình của khách theo chính sách tenant |
| `restricted`   | Số CCCD, lương, số tài khoản                                  | Che trước khi tới mô hình; chỉ mô hình cục bộ nếu tenant cho phép                       |

Gateway còn lo chọn mô hình theo profile, ngân sách token, thử lại và đổi đích,
và quan sát. Dữ liệu cá nhân được gắn nhãn khi nhập. Trường `restricted` bị
che trước khi tới bất kỳ mô hình nào, trừ đích tenant cho phép (`SEC04`). Chỉ
dùng nhà cung cấp có cam kết không huấn luyện trên dữ liệu khách, và gateway từ
chối đích không có cam kết (10.4, hàng Không huấn luyện); `SEC11` viết việc từ
chối là "với mọi nhãn trên `public`". Hai câu lệch nhau ở nhãn `public`, xem
điểm mở. Trace chỉ mang định danh an toàn, phiên bản, độ trễ, token; không
nội dung, không giá. Logic nghiệp vụ không đổi khi đổi đích. Lý do tài liệu
nêu: nền tảng đã có model gateway và thang phân loại trong knowledge, nên mở
rộng thành bảng định tuyến. Q15 ("mô hình nào được đọc dữ liệu nào") được trả
lời bằng chính quy tắc này.

## Phương án đã cân nhắc

Tài liệu không nêu phương án khác. Digest cho thấy một phương án đang có thật:
để proxy OpenAI-compatible ngoài ứng dụng (`OPENAI_BASE_URL`, ví dụ LiteLLM)
chọn đích theo tên mô hình. Chat, embedding OpenAI-compatible và parser tài
liệu đã đi qua proxy này (`configs/models/gateway.yaml:4-6`;
`apps/api/src/dw_api/bootstrap/models.py:51, 91`;
`apps/worker/src/dw_worker/composition.py:115, 177`). Nhưng request tới proxy
không mang nhãn, Deepgram và TEI đi vòng qua nó, và ứng dụng không tự chứng
minh được `SEC11`.
Chọn cách này thì cấu hình proxy thành artifact quyết định an ninh, phải có
phiên bản và nằm trong release manifest (MODEL-01, MODEL-16).

## Hệ quả

- Nhãn `public`, bảng định tuyến và bước che là thay đổi nền tảng, xuyên
  `dw_agent_runtime`, `dw_knowledge` và hai app (MODEL-20). Chúng lên `main`
  trước rồi mới merge vào `bidding` (`.claude/plans/bidding.md:15-18`).
- Chính sách mô hình của tenant là lớp tenant của `TenantOverlay`: nạp lúc chạy
  từ storage, không từ checkout, và rơi về lớp platform, không sang tenant khác
  (CLAUDE.md, mục Per-tenant artifacts).
- Scaffold hiện chỉ cấm context import `dw_api`, `dw_worker`, `dw_docgen`
  (`scripts/new_context.py`, contract `<Context> is independent`); contract cấm
  framework và provider trong domain chỉ áp cho `dw_platform.domain`
  (`pyproject.toml:270-272`). Muốn graph và domain của `dw_bid` không gọi SDK
  nhà cung cấp thì phải thêm contract import-linter khi scaffold (MODEL-01).
- Span `dw.model.call` chỉ mang id, phiên bản, profile, nhà cung cấp, tên mô
  hình, token, độ trễ
  (`dw_agent_runtime/adapters/telemetry_usage.py:40-67`); thêm nhãn hay đích
  vào span vẫn giữ mức đó. Giá không vào trace, xem
  [ADR 0007 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0007-bid-price-visible-to-pricing-and-owner-only.md).

## Xung đột và điểm mở

Mục 10.3 (`process.md:718-720`) nói nền tảng đã có gateway, model profile và
thang `internal < confidential < restricted`. Hiện trạng trong code:

| Theo 10.3                                 | Hiện trạng                                                                                                                                                                                            |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mọi lời gọi qua gateway                   | `RoutingModelGateway` có, nhưng agent loop, compaction, embedding, parser `/responses`, Deepgram đi vòng qua nó (MODEL-01)                                                                            |
| Định tuyến theo nhãn                      | Chưa có: `ModelRequest` không có trường nhãn, `_route` chỉ rẽ theo `route_kind`, `task` (MODEL-06)                                                                                                    |
| Thang phân loại                           | `_CLEARANCE_ALLOWS` ở `dw_knowledge/contracts.py:23-27` là bảng quyền đọc theo clearance; không có `public`, cột không có CHECK (MODEL-04, MODEL-05)                                                  |
| Model profile                             | Có, nhưng không có đích, vùng, cam kết, nhãn tối đa; endpoint là một `OPENAI_BASE_URL` cho cả tiến trình (MODEL-02, MODEL-16)                                                                         |
| `TenantOverlay` trên profile ("cần thêm") | Đã có (`dw_agent_runtime/model/profiles.py:89`), nhưng chỉ lớp platform được nạp (`load_directory`); agent loop resolve không theo tenant (MODEL-09)                                                  |
| Che dữ liệu; từ chối đích                 | Chưa có; `dw_observability/redaction.py` chỉ che theo tên khóa bí mật (password, token, api_key…) và Bearer token, cho trace, audit, thẻ duyệt; không nằm trên đường tới mô hình (MODEL-07, MODEL-08) |
| Ngân sách, thử lại, đổi đích              | Ngân sách và thử lại có ở cả hai đường; route `fallback` chỉ trên đường structured, agent loop giao đổi đích cho proxy (`adapters/model_retry.py:9-14`); fallback không xét nhãn (MODEL-10)           |

- **Điểm thực thi.** `SEC03` nói "mọi lời gọi", nhưng
  `dw_agent_runtime/adapters/run_budget.py:3-8` gọi agent loop là "a bare chat
  model the gateway never sees" (MODEL-01). Cần quyết việc định tuyến và che
  đặt ở seam nào (`ModelGateway`, `ChatModelFactory`, embedding, parser), mỗi
  seam có test đi thẳng vào nó.
- **Nhãn thiếu hoặc lạ.** `classification` mặc định `'internal'` ở DB, API và
  knowledge; web không gửi nhãn (MODEL-15). Theo bảng định tuyến, dữ liệu quên
  nhãn sẽ ra cloud; tài liệu im lặng. Cần quyết nhãn thiếu hoặc lạ tính là mức
  nào, ai gắn nhãn, và nhãn của lời gọi tính từ dữ liệu đã lưu hay do node khai.
- **Chủ của thang.** `dw_agent_runtime` không phụ thuộc `dw_knowledge` (MODEL-20).
  `rule-spec.md:100` thiếu `public`, trái `process.md:713` và `SEC11`. Thêm
  `public` mà không sửa `_CLEARANCE_ALLOWS` thì không ai đọc được tài liệu
  `public` (MODEL-04, MODEL-05). Cần quyết thang nằm ở đâu để gateway và
  knowledge cùng đọc một bản.
- **Che trường `restricted`.** Nhãn chỉ có ở cấp tài liệu, memory, evidence,
  không có cấp trường (MODEL-18). Parser gửi nguyên file hoặc ảnh lên mô hình
  lúc ingest, và `DocumentParserPort.parse` không nhận nhãn (MODEL-14). Tìm
  CCCD bằng mô hình cloud thì CCCD đã ra cloud (MODEL-07). Cần quyết có parser
  và bộ nhận diện cục bộ không; việc này đảo quyết định đã bỏ parser cục bộ,
  xem thêm
  [ADR 0007](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/adr/0007-document-content-turns-cannot-call-outbound-tools.md).
- **Đích và cam kết.** Route chỉ nêu kiểu adapter và tên mô hình, không nêu
  endpoint (`dw_agent_runtime/model/profiles.py:28-50`), nên một cam kết khai
  trên route không chỉ ra đích thật. Nếu mặc định là "không có cam kết" (fail
  closed), profile chưa khai thì không dùng được cho nhãn trên `public`, tức cả
  6 file hiện có trong `configs/models` phải khai lại (MODEL-02, MODEL-08). Cần
  quyết cam kết gắn ở cấp nào, cách mô hình hóa đích, và fallback có bị giới
  hạn ở đích cùng mức hay chặt hơn không (MODEL-10).
- **Phạm vi "không huấn luyện".** `process.md:737` từ chối mọi đích không cam
  kết; `SEC11` chỉ áp cho nhãn trên `public`; `process.md:713` cho `public` đi
  "mô hình cloud qua gateway" (MODEL-08). DOCS-55 lưu ý E-HSMT công khai vẫn lộ
  việc tenant dự gói nào. Cần chốt một câu cho nhãn `public`.
- **Embedding.** Một collection chỉ có một độ rộng vector, nên không đổi
  embedder theo nhãn từng chunk; câu truy vấn cũng tới embedder (MODEL-13). Cần
  chọn một embedder cục bộ cho mọi dữ liệu `dw_bid`, hay collection riêng theo
  nhãn.
- **Truy vết và số đo.** Manifest không ghim model profile, run không ghi
  profile, gateway không trả route đã trả lời (MODEL-03, MODEL-17). Bản ghi đo
  `docs/architecture/model-gateway-findings.md` mà code trỏ tới không tồn tại
  (MODEL-19). Cần quyết có ghim bảng định tuyến và ghi đích đã dùng lên run
  không, và đo lại từng đích trước khi đưa vào bảng.

Các mã như `TEN-02`, `DOCS-15` là mục trong [bản đối chiếu tài liệu với repo ngày 29/9/2026](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/audit-2026-09-29.md).
