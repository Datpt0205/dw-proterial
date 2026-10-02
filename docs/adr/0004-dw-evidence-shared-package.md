---
status: Proposed
date: 2026-09-29
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#hướng-đi-sau-phản-biện
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#21-sản-phẩm-là-gì
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#91-dùng-lại-được
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#101-vị-trí-trong-codebase
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#11-quyết-định-thiết-kế-đã-chốt
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#131-dựng-hoàn-chỉnh-theo-phụ-thuộc
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#21-dữ-kiện-có-neo-nguồn
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#34-đính-chính-dữ-kiện
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#8-hàm-hỗ-trợ-dùng-chung
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#10-bố-cục-mã-nguồn
---

# Tách `dw_evidence` làm package nền tảng dùng chung

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

Vòng phản biện kiến trúc của [tài liệu quy trình](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md)
đề nghị một khung "Domain Pack" chung cho mọi nghiệp vụ. Tài liệu điều chỉnh đề
nghị đó: không dựng khung trừu tượng trước, vì repo yêu cầu tránh abstraction
rỗng. Chỉ phần đã có hai nơi dùng, DW01 (`dw_tender`) và E-HSDT, được đưa xuống
nền tảng: định vị trích dẫn, neo nguồn, chấm điểm, tra luật (process, "Hướng đi
sau phản biện", hàng Khung "Domain Pack"; Q16).

Quyết định: phần đó thành package nền tảng mới `dw_evidence`, không phải context.
Lý do tài liệu nêu: hai context cùng dùng, mà context không được import nhau,
nên theo quy tắc repo nó không nằm trong một context được (process 10.1;
[đặc tả quy tắc](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md) mục 10). Mã của DW01 được
chuyển xuống, không sao chép. Riêng `evidence_locator.locate_quote` được "dùng
nguyên, không viết lại", làm nền của `SourceAnchor` cho mọi yêu cầu và mọi bằng
chứng; `SourceAnchor.start_offset` lấy từ hàm này (process 9.1; rule-spec 2.1,
8). ADR này và package thuộc luồng A, "bắt đầu ngay"; luồng B (lõi kiểm soát)
phụ thuộc `dw_evidence` (process 13.1). Đây là khuyến nghị của tài liệu quy
trình v0.4 (29/9/2026), chưa được kiểm chứng bằng phỏng vấn.

## Phương án đã cân nhắc

- **(a) Khung "Domain Pack" chung.** Tài liệu không dựng trước: "Không dựng
  khung trừu tượng trước", vì repo yêu cầu tránh abstraction rỗng (hàng Khung
  "Domain Pack"; Q16).
- **(b) Package nền tảng `dw_evidence`.** Lựa chọn của tài liệu, và là đề xuất
  của ADR này. Process 10.1 nêu thêm một biến thể: đặt phần này vào
  `dw_knowledge` thay vì package mới.
- **(c) Giữ trong context cho tới khi repo này có nơi dùng thứ hai thật.** Đây
  là khuyến nghị trong area plan (của Claude, chờ Đạt chốt): "The core stays
  inside `dw_bidding` until EUDR is a real second consumer"
  (`.claude/plans/bidding.md:50-51`), dựa trên
  `.claude/rules/code-quality.md:138-140`. Phương án này còn sống vì DW01 không
  có trong repo này (SCAF-10, DW01-07, RULES-10): `packages/python` chỉ có tám
  package nền tảng, và `git grep` không thấy `dw_tender`, `evidence_locator`
  hay `locate_quote` ngoài `docs/products/` và `bidding.md:75`.

## Hệ quả

- `dw_bid` phụ thuộc `dw_evidence`: `start_offset` của `SourceAnchor` lấy từ
  `locate_quote` (rule-spec 2.1). Luồng B chờ package này (process 13.1).
- `dw_evidence` nằm ngoài context, nên là thay đổi nền tảng. Theo area plan, nó
  lên `main` trước rồi mới merge vào nhánh `bidding`
  (`.claude/plans/bidding.md:15-19`).
- `make new-context` chỉ dựng context. CLAUDE.md không có quy trình cho package
  nền tảng mới, nên các chỗ đăng ký tương tự bước 2 và 7 của context phải làm
  tay (SCAF-15).

## Xung đột và điểm mở

1. **Tiền đề "hai nơi dùng" không đúng trong repo này.** DW01 nằm ở repo khác
   (`C:\Users\phung\dw`); ở đây chỉ `dw_bid` sẽ gọi `dw_evidence` (SCAF-12,
   DW01-07, DOCS-32). `code-quality.md` chỉ tách khi caller thứ hai đã có
   thật, "not ahead of one" (`:102-103`, `:138-140`). Rule-spec 10 dựa đúng
   vào tiền đề này để nói package "không thể nằm trong một context". Cần
   quyết: chọn (b) kèm consumer thứ hai có thật hoặc lý do đi ngược
   `code-quality.md`, hay chọn (c).

2. **"Chuyển, không sao chép" và "dùng nguyên" không làm được như viết.** Area
   plan ghi mã cũ "is reference material: re-implement from it, do not copy it"
   (`bidding.md:71-72`); DW01 ở repo khác nên "chuyển xuống" thực chất là chép
   sang (SCAF-11, DW01-06). Bản cũ cũng chưa đáp ứng `SourceAnchor` (DW01-05;
   đã kiểm lại `dw_tender/domain/services/evidence_locator.py` của repo cũ):
   khớp sau khi gộp khoảng trắng, chuẩn hóa NFC và casefold (`:23-25`), nên
   không phải nguyên văn chặt; `source_hash` là sha256 của text truyền vào
   (`:59`), không phải của file gốc như rule-spec 2.1 ghi; không có số trang.
   Chạy lại với nguồn "Hồ sơ dự thầu có hiệu lực 120 ngày…" ở dạng NFD, quote
   "hiệu lực 120 ngày" trả offset lệch: đoạn cắt ra bắt đầu giữa chữ "thầu".
   Cần quyết: viết lại theo tham khảo hay port rồi sửa; hash tính trên file gốc
   hay trên text đã bóc.

3. **Phạm vi của `dw_evidence` lệch giữa các đoạn.** Hàng "Hướng đi" và process
   10.1 gồm cả chấm điểm (`scoring_engine`) và chuỗi tra luật; 10.1 còn để ngỏ
   nơi đặt (`dw_knowledge` hoặc package dùng chung). Rule-spec 10 chỉ ghi
   `locate_quote`, anchors, `vn_text helpers`, không nói helpers gồm hàm nào;
   rule-spec 8 chỉ đánh dấu `locate_quote` là "chuyển xuống tầng dùng chung".
   Rule-spec 10 còn đặt `SourceAnchor` trong `dw_bid/domain/facts.py`, trong
   khi lại ghi `dw_evidence` giữ "anchors". Hình 1 (`process.md:149`) đặt cả
   "Rule engine" ở nền tảng, còn rule-spec 10 đặt registry quy tắc trong
   `dw_bid` (SCAF-17). Code cũ cho thấy chấm điểm gắn với nghiệp vụ:
   `scoring_engine.py:13` import `Requirement`, `ComplianceFinding` từ
   `dw_tender.domain.entities` (SCAF-14), và
   `validate_requirements` từ chối bộ tiêu chí không có trọng số, trong khi 9.1
   ghi E-HSMT xây lắp chủ yếu đánh giá đạt, không đạt (DW01-09). Chuỗi tra luật
   cũ nằm trong `dw_knowledge` của repo cũ, còn `verified_constraint` nằm trong
   `dw_tender` (DW01-11, DW01-12). Cần quyết: danh sách thành phần của
   `dw_evidence`, và phần nào ở lại `dw_bid` hay vào `dw_knowledge`.

4. **Nền tảng đã có một hình neo nguồn.** `EvidenceRef` và bảng
   `knowledge.evidence` có `page`, `start_offset`, `end_offset`, `quote`,
   `provenance_hash`
   (`packages/python/dw_knowledge/src/dw_knowledge/contracts.py:82-97`;
   `db/migrations/versions/0007_evidence.py:58-83`). Nhưng `provenance_hash` là
   sha256 của một chunk (`dw_knowledge/chunking.py:36-37`), và store bắt
   evidence phải nêu chunk (`dw_knowledge/adapters/evidence_store.py:72, 96`).
   Tên "Evidence" cũng đã mang nghĩa khác ở nền tảng (SCAF-13, DW01-08,
   RULES-10). Cần quyết: mở rộng neo của `dw_knowledge`, ánh xạ `SourceAnchor`
   sang `EvidenceRef`, hay để `dw_evidence` giữ một hình neo riêng; và tên
   package.

5. **Neo cho giá trị không có câu trong nguồn.** `SourceAnchor.quote` phải là
   nguyên văn đã tìm thấy (rule-spec 2.1). Đính chính đòi "neo nguồn chứng minh
   giá trị đúng" khi OCR đọc sai (rule-spec 3.4), nhưng khi đó câu chứa giá trị
   đúng có thể không có trong text đã bóc. Fact thị giác của A06 (chữ ký, dấu)
   cũng không có câu (DOCS-16). Cần quyết: `dw_evidence` có thêm loại neo khác
   câu nguyên văn hay không.

6. **Hướng phụ thuộc chưa được kiểm.** Contract import-linter chung cho các
   package nền tảng ("Platform packages do not import app composition roots")
   chỉ cấm `dw_api`, `dw_worker`, `dw_docgen` (`pyproject.toml:335-346`);
   không contract nào cấm nền tảng import một context (ART-18). Cần quyết:
   contract nào giữ `dw_evidence` không import `dw_bid`, thêm trong cùng thay
   đổi.

7. **Thời điểm.** Luồng A ghi "bắt đầu ngay" (process 13.1). Area plan đặt
   phỏng vấn trước code sâu, và slice đầu sau scaffold là bóc yêu cầu E-HSMT
   kèm câu gốc (`bidding.md:63, 97-100`; RULES-09). Thứ tự xây ở
   [ADR 0012 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0012-full-scope-built-in-dependency-order.md).
   Cần quyết: dựng `dw_evidence` trước slice đầu, hay khi slice đó cần nó.

Các mã như `TEN-02`, `DOCS-15` là mục trong [bản đối chiếu tài liệu với repo ngày 29/9/2026](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/audit-2026-09-29.md).
