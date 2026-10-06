# 01 — Lọc tài liệu trong Qdrant, một builder embedding, prompt agent loop có version

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Ba sửa nhỏ, mỗi cái một chủ cho một sự thật: tài liệu nào được hỏi (trong bộ lọc
Qdrant), model nào embed (một builder), prompt nào agent loop dùng (registry). Spec, mục
"Quy tắc và quyết định" và "Quy tắc và kiểm soát".

## Việc cần làm

1. **Lọc tài liệu trước top-k**
    - `dw_knowledge/gateway.py` `search`: truyền `query.document_ids` xuống index;
      gỡ dòng lọc sau (`gateway.py:581-582`).
    - `adapters/qdrant_index.py` `search`: tham số `document_ids: Sequence[UUID] = ()`;
      không rỗng thì thêm `FieldCondition(key="source_document_id",
      match=MatchAny(any=[...]))` vào `must`, cạnh các điều kiện của `trusted_filter`.
      Cập nhật `VectorIndexPort` và mọi fake.
    - Test tích hợp (Qdrant thật): 30 chunk của tài liệu khác giống câu hỏi hơn 5 chunk
      của tài liệu D; hỏi `document_ids=[D]`, `top_k=5` → đủ 5 chunk, đều của D.
    - `test_qdrant_tenant_filter.py`: biến thể có `document_ids` của tenant B gọi dưới
      tenant A → 0 kết quả.
2. **Một builder embedding**
    - Một hàm dùng chung (đặt ở chỗ cả api lẫn worker đã phụ thuộc; kiểm
      `pyproject.toml` import-linter trước khi chọn) nhận provider, route embedding đã
      resolve, base URL, key; trả `EmbeddingPort`; giữ `ConfigError` cho provider lạ và
      route thiếu `dimensions`.
    - `apps/api/.../bootstrap/knowledge.py` và `apps/worker/.../composition.py` gọi nó;
      xóa thân hàm cũ. Sửa docstring worker; xóa chuỗi docstring chết.
    - Test: cả hai app, cùng settings, dựng adapter cùng `model` và chiều; provider lạ →
      `ConfigError` ở cả hai.
3. **Prompt agent loop có version** (chỉ khi gọn như spec mô tả; nếu không, theo Câu hỏi 1
   của spec)
    - `AgentSpec`: bỏ `render_prompt`; thêm `prompt_id`, `prompt_version`,
      `prompts: PromptRegistry`, `prompt_variables: Callable[[ModelRequest], dict[str,
      str]]` (biến theo từng lần gọi: ngày, màn hình đang xem).
    - `WorkerSystemPrompt`: render bằng `prompts.render(id, version, variables,
      tenant_id=<RunContext của request>)`.
    - Runner: ghi chi phí agent loop bằng prompt id/version đã pin (từ
      `WorkerDefinition` nếu chọn phương án đề xuất); xóa `AGENT_LOOP_PROMPT_VERSION`.
    - `scripts/release_manifest.py`: prompt đó vào manifest như mọi prompt khác.
    - Sửa test `test_agent_factory.py` và các test dựng `AgentSpec`.

## Tiêu chí chấp nhận

- Các test ở trên, cộng:
    - ledger của một run agent ghi `prompt_id`/`prompt_version` của registry, không
      `0.0.0`;
    - tenant A có bản prompt riêng: run của A render bản đó, run của B render bản
      platform (fallback không sang ngang);
    - prompt không có trong registry → lỗi khi build agent.
- Chứng minh đỏ cho từng dòng bảng "Quy tắc và kiểm soát" của spec, ghi dưới
  `## Comments`.
- `rg "AGENT_LOOP_PROMPT_VERSION|render_prompt" packages apps` không còn kết quả (trừ
  ghi chú lịch sử nếu có).
- `make ci` xanh; `make infra-down` cho repo này khi xong.

## Nguồn

- Audit harness 6/10/2026: khu `retrieval` gap "document_ids is applied after top-k";
  khu `memory-store` gap "Two embedding builders" (real=true); khu
  `file-memory-and-instructions` gap "The agent-loop system prompt is not a versioned
  artifact".
- `gateway.py:575-610`, `adapters/qdrant_index.py:183-305`,
  `apps/api/src/dw_api/bootstrap/knowledge.py:20-55`,
  `apps/worker/src/dw_worker/composition.py:100-150`, `agent_factory.py:108-180`,
  `system_prompt.py`, `langchain_usage.py:50-100`, `langgraph_runner.py:210-220`,
  `model/prompts.py:50-100`, `contracts.py:50-80`.
- `CLAUDE.md` "Per-tenant artifacts", "Qdrant retrieval always receives trusted
  tenant/workspace/ACL filters"; `failure-modes.md` #2, #3.

## Comments
