# 01 — Phân loại theo bằng chứng, độ tin do workflow tính, CHECK, lớp retention trung thực

Status: ready-for-agent
Blocked by: platform-runtime/memory-vectors 01
Area: platform-runtime

## Mục tiêu

Một memory chỉ được lưu ở phân loại, workspace và độ tin mà code đã kiểm, và các cột tập
cố định của nó bị database từ chối khi sai. Spec, mục "Quy tắc và quyết định" và "Quy tắc
và kiểm soát".

## Việc cần làm

1. **Bằng chứng** — `packages/python/dw_knowledge/src/dw_knowledge/adapters/evidence_store.py`:
    - Truy vấn chunk join `knowledge.documents`, lấy thêm `chunks.workspace_id`,
      `documents.classification`, `documents.scope`.
    - Từ chối (`DomainError`, nêu `chunk_id`) chunk có `workspace_id` khác workspace của
      người gọi, trừ khi tài liệu `scope = 'global'` (cùng luật với
      `KnowledgeGateway.search`; đọc luật đó từ một chỗ nếu tách được, đừng chép lần hai).
    - Ghi `knowledge.evidence.classification` từ tài liệu, không từ `ref.classification`.
    - `record` trả về phân loại chặt nhất trong các tài liệu được trích (thứ tự lấy từ
      thang clearance ở `dw_knowledge/contracts.py`, không gõ lại). Cập nhật
      `EvidenceStorePort` (`dw_memory/ports.py`) theo.
2. **Phân loại** — `dw_memory/service.py`: sau `record`, nếu phân loại candidate khai
   thấp hơn phân loại trả về thì raise `DomainError` (giao dịch rollback, không item,
   không candidate row). `MemoryCandidate.classification` thành `Literal` của ba giá trị,
   hoặc validator đọc khóa thang clearance; giá trị lạ bị từ chối khi parse.
3. **Độ tin** — `dw_memory/policy.py`, `dw_memory/service.py`, `consumers/memory.py`:
    - Docstring `MemoryCandidate`, `MemoryWritePolicy` và `MemoryProposePort` nói: độ tin
      do code workflow tính từ tín hiệu đã kiểm, không bao giờ chép từ đầu ra model.
    - Cưỡng chế ở cửa vào duy nhất từ producer: `MemoryCandidatePayload` lên
      `schema_version` `1.1`, không còn mang `confidence` thô; mang tín hiệu (đề xuất ở
      spec, Câu hỏi 1). Service tính độ tin từ tín hiệu và từ số bằng chứng đã qua kiểm.
      Payload `1.0` bị từ chối là `UndeliverableEventError` (đóng chặt, không đoán).
    - Nâng `MemoryWritePolicy.policy_version` (hành vi đổi); release manifest đọc nó.
    - `dw_evals/graders.py:199` dựng `MemoryCandidate`: sửa theo hình dạng mới.
4. **Lỗi từ chối không bị thử lại vô hạn**: kiểm handler outbox xử lý `DomainError` từ
   `propose` thế nào; nếu nó đang được thử lại như lỗi hạ tầng thì ánh xạ sang
   `UndeliverableEventError` (bằng chứng sai không thành đúng khi thử lại).
5. **CHECK** — `uv run alembic revision -m "memory fixed-set checks"` (id hex ngẫu nhiên,
   số thứ tự chỉ ở tên tệp): CHECK trên `memory.items.memory_type`, `classification`,
   `memory.write_candidates.decision`, `memory_type`, `classification`. Tên theo
   `NAMING_CONVENTION`. Đo trước dữ liệu có sẵn (DB dev) để migration không hỏng trên
   dòng cũ; downgrade gỡ chúng. Không CHECK cho `retention_policy` (spec).
6. **Retention** — `configs/policies/retention@<bản kế>.yaml`: gỡ `sensitive`,
   `ephemeral`, `legal_hold` khỏi `classes`, ghi chú vì sao và khi nào `legal_hold`
   quay lại. Đổi mọi chỗ ghim tên tệp (`rg "retention@1.4.0"`). Test
   `test_legal_hold_is_never_swept_however_old` chuyển sang chính sách giả có một lớp
   `days: null`, để hành vi vẫn được giữ.

## Tiêu chí chấp nhận

- Test âm, mỗi cái một chốt của spec:
    - candidate `internal` trích chunk của tài liệu `confidential` → bị từ chối, 0 item,
      0 dòng candidate;
    - candidate `confidential` trích đúng tài liệu `confidential` → ghi, item mang
      `confidential`, `knowledge.evidence.classification = 'confidential'` dù ref khai
      `internal`;
    - chunk của workspace W2 làm bằng chứng cho memory ở W1 (cùng tenant) → bị từ chối;
    - chunk của tài liệu global → được chấp nhận;
    - payload có `confidence: 1.0` (dạng model tiêm) → không AUTO_WRITE; payload `1.0` cũ
      → `UndeliverableEventError`;
    - chèn `memory_type = 'bogus'`, `decision = 'maybe'`, `classification = 'public'` →
      `IntegrityError`, tên ràng buộc đúng;
    - test đọc `pg_constraint` so tập giá trị CHECK với `MemoryType`, `WriteDecision`,
      khóa thang clearance;
    - test: mọi lớp memory trong chính sách retention đang ghim có đường gán trong code
      (hôm nay: chỉ `default`).
- Chứng minh đỏ cho từng dòng của bảng "Quy tắc và kiểm soát" (gỡ chốt, test đỏ, hoàn
  nguyên), ghi dưới `## Comments`.
- `make ci` xanh; `make infra-down` cho repo này khi xong.

## Nguồn

- Audit harness 6/10/2026, khu `memory-store`: gap phân loại theo chunk, gap độ tin
  AUTO_WRITE, gap CHECK (real=true, kèm cảnh báo về `retention_policy`), gap lớp
  retention.
- `service.py:87-216, 391-470`, `policy.py`, `ports.py`, `evidence_store.py:55-125`,
  `dw_knowledge/contracts.py:14-37`, `dw_knowledge/tables.py:12-55`,
  `apps/worker/src/dw_worker/consumers/memory.py:87-160`,
  `db/migrations/sql/0001_platform_baseline.sql:97-139`,
  `configs/policies/retention@1.4.0.yaml`, `dw_platform/retention_policy.py`.
- `CLAUDE.md` "Agent and tool rules", "Data model rules"; `failure-modes.md` #1, #2, #3, #7.

## Comments
