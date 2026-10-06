# 01 — Xóa vector memory theo id và theo tenant; ranker lọc theo id đã gọi lên

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Point trong collection `dw_memory` không sống lâu hơn dòng `memory.items` của nó (hết
hạn, bị thay thế, tenant rời đi), và `nearest` chỉ xếp lại đúng các id mà SQL đã gọi lên.
Spec, mục "Hiện trạng" và "Quy tắc và kiểm soát".

## Việc cần làm

1. `packages/python/dw_memory/src/dw_memory/ranking.py`:
    - Protocol mới `MemoryVectorPurgePort` với `delete(memory_ids)` và
      `delete_by_tenant(tenant_id)`. Không gộp vào `MemoryRankerPort`: recall chỉ cần
      `nearest` (`code-quality.md`, interface segregation).
    - `MemoryRankerPort.nearest` nhận thêm `candidate_ids: Sequence[UUID]` (bắt buộc,
      không có mặc định: một bộ lọc quên được là một bộ lọc sẽ bị quên).
    - Sửa docstring module: câu "A superseded memory may well still sit in the index"
      không còn đúng sau ticket này.
2. `adapters/qdrant_ranker.py`:
    - `nearest`: thêm `models.HasIdCondition(has_id=[str(i) for i in candidate_ids])`
      vào `must`, cạnh ba điều kiện tenant, workspace, worker (không thay chúng);
      `limit=len(candidate_ids)`; tập rỗng thì trả `()` không gọi Qdrant.
    - `delete(memory_ids)`: `PointIdsList`. `delete_by_tenant`: `FilterSelector` theo
      `tenant_id` (field đã có payload index). Collection chưa tồn tại thì là việc đã
      xong, không lỗi. Lỗi khác thì raise: người gọi quyết định (khác `index`, vốn nuốt
      lỗi vì chạy sau commit).
3. `dw_memory/service.py`:
    - `_ordered` truyền `candidate_ids=[item.memory_id for item in found]`.
    - Sau khi giao dịch `propose` commit, nếu `superseded` không rỗng và service có
      purge port, gọi `delete(superseded)`. Lỗi thì log cảnh báo, không làm hỏng
      `propose` (memory đã commit; point thừa chỉ tốn chỗ vì ranker giờ chỉ xếp id SQL
      chọn). Thêm field `vector_purge: MemoryVectorPurgePort | None = None` vào
      `MemoryService`, nối ở worker.
4. `dw_memory/retention.py`: `SqlMemoryRetention` nhận
   `vector_index: MemoryVectorPurgePort | None`, theo đúng mẫu `SqlKnowledgeRetention`. `_delete_batch`
   trả về id đã xóa (`RETURNING memory_id`), rồi xóa point của các id đó sau commit.
   Nếu Qdrant lỗi: ghi log và đếm, dòng đã xóa không khôi phục; ghi trong docstring rằng
   lượt quét sau không thấy lại các id đó, và vì vậy offboarding vẫn là lưới cuối.
5. `apps/worker/src/dw_worker/consumers/offboarding.py`: `TenantOffboardingLane` nhận
   thêm `memory_vectors: VectorPurgePort` (cùng Protocol `delete_by_tenant` đã có) và
   gọi sau `vector_index.delete_by_tenant`. `main.py` nối cùng một `QdrantMemoryRanker`
   cho cả ba chỗ (handler, retention, offboarding). Không Qdrant thì không nối.
6. Docstring `TenantOffboardingLane` và `offboarding.py` (dw_platform) nói hai
   collection, không một.

## Tiêu chí chấp nhận

- Test tích hợp với Qdrant thật (`packages/python/dw_memory/tests/integration/test_qdrant_ranker.py`
  và test lane offboarding của worker):
    - offboarding: tenant A và B mỗi bên có point; chạy lane cho A; A còn 0 point, B còn
      nguyên;
    - retention: memory quá hạn bị xóa dòng thì mất point; memory còn hạn giữ point;
    - supersession: memory bị thay (cùng `fact_key`, cùng subject) mất point; memory mới
      còn point;
    - `nearest`: một worker có nhiều memory ở subject khác hơn tập `found`; kết quả chỉ
      chứa id thuộc `candidate_ids`, đủ cả tập;
    - `test_an_id_the_ranker_invents_cannot_add_a_row` và mọi test tenant, worker của
      ranker giữ xanh.
- Chứng minh đỏ, ghi lệnh và kết quả dưới `## Comments`: bỏ lần lượt bốn chốt ở bảng
  của spec, mỗi lần một test đỏ; hoàn nguyên.
- `uv run pytest packages/python/dw_memory apps/worker -m integration` và `make ci` xanh;
  `make infra-down` cho repo này khi xong.
- Không tên sản phẩm hay context nào trong tệp đã sửa.

## Nguồn

- Audit harness 6/10/2026, khu `memory-store` gap 1 (real=true), khu `retrieval` gap
  "The vector ranker asks Qdrant the wrong question", khu `file-memory-and-instructions`
  gap 1.
- `qdrant_ranker.py:97-174`, `ranking.py`, `service.py:132-216, 266-301, 487-522`,
  `retention.py:41-104`, `apps/worker/src/dw_worker/consumers/offboarding.py:100-161`,
  `apps/worker/src/dw_worker/main.py:140-200`.
- `.claude/rules/failure-modes.md` #1, #3, #5, #6.

## Comments
