# 01 — Compaction nén được vòng tool dài và giữ mỏ neo; checkpoint có thời hạn

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Compaction làm đúng việc nó tồn tại để làm (một vòng tool dài, một thread nhiều lượt),
đầu vào bộ tóm tắt có ngân sách do profile sở hữu, và checkpoint của run đã xong không
nằm mãi. Spec, mục "Quy tắc và quyết định" và "Quy tắc và kiểm soát".

## Việc cần làm

1. **Đo trước** (`failure-modes.md` #4): dựng lại hai trường hợp của audit với
   `langchain` đang ghim (không gọi model; bộ tóm tắt giả ghi lại đầu vào). Ghi số vào
   `## Comments`. Đây cũng là hai test đầu tiên, và phải đỏ trước khi sửa.
2. `model/profiles.py`: `ModelRoute.max_input_tokens: int | None` (gt=0). Route tóm tắt
   trong `configs/models/*.yaml` khai giá trị. `CompactionSpec`/`platform_middleware`
   đọc nó qua `ModelProfileRegistry.resolve(summary_profile_id, tenant_id=...)`;
   thiếu → `ConfigError` khi build.
3. `context_compaction.py`:
    - Không dùng `_trim_messages_for_summary` của thư viện cho đầu vào bộ tóm tắt. Chia
      đoạn bị gỡ thành các khúc vừa ngân sách (đếm bằng `token_counter` của middleware),
      không tách một AIMessage gọi tool khỏi ToolMessage của nó, không đòi khúc bắt đầu
      bằng HumanMessage.
    - Tìm summary hệ thống lần trước (`additional_kwargs["dw_system_generated"]`) trong
      đoạn bị gỡ; đưa nó vào lời gọi đầu tiên như mỏ neo, prompt bảo "cập nhật bản này",
      và mỗi khúc sau nhận summary của khúc trước làm mỏ neo. Nếu prompt tóm tắt cần câu
      mới thì ra bản copy runtime mới có version; không sửa bản cũ tại chỗ.
    - Mỗi lời gọi: `_budget.check` trước, `_budget.record` sau.
    - Một khúc lỗi → bỏ cả lần nén, lịch sử giữ nguyên (như hiện nay).
    - Sửa docstring `_record`: digest chứng minh phần bị gỡ; các checkpoint trước vẫn giữ
      nguyên văn cho tới khi lane tỉa xóa chúng.
4. `tests/unit/test_context_compaction.py`: sửa docstring module cho khớp test có thật;
   thêm test "lịch sử quá dài cho một lần vẫn được nén" đúng như nó nói.
   `test_history_too_large_to_summarise_is_not_traded_for_a_placeholder` chuyển sang điều
   kiện thật còn lại.
5. **Tỉa checkpoint:**
    - Migration mới (`uv run alembic revision -m "..."`): policy `worker_drain_*` cho
      `platform.run_checkpoints` và `run_checkpoint_writes` theo mẫu
      `0010_memory_retention_drain.py`; index phục vụ lượt quét (dẫn đầu bằng cột lượt
      quét lọc, xem `CLAUDE.md` "Data model rules"). Grants đi cùng migration;
      `test_rls_coverage.py`, `test_privileges.py` xanh.
    - `retention_policy.py` + `configs/policies/retention@<bản kế>.yaml`: khối
      `checkpoints` (`superseded_days`, `idle_thread_days`); đổi mọi chỗ ghim tên tệp.
    - Một class retention (cạnh `checkpoint.py`, theo kiểu `SqlMemoryRetention`): lô có
      giới hạn, chỉ thread không có run ở trạng thái khác `completed/failed/cancelled`;
      xóa writes rồi checkpoints; nối vào lane `retention` ở `apps/worker/src/dw_worker/main.py`.
    - `adelete_thread`: giữ raise, sửa thông điệp trỏ tới lane.
6. Test offboarding: một tenant có checkpoint; sau `purge_rows` còn 0 dòng ở cả hai bảng.

## Tiêu chí chấp nhận

- Hai test đo của bước 1 đỏ trên code cũ, xanh sau sửa; số đo trước/sau trong Comments.
- Test: ngân sách 2000 so với 8000 cho số token đầu vào mỗi lời gọi khác nhau tương ứng;
  route thiếu `max_input_tokens` → `ConfigError`.
- Test: approval đang chờ vẫn sống qua compaction (test hiện có xanh); ledger có một
  mục cho mỗi khúc.
- Integration: thread đã xong có 5 checkpoint cũ → còn đúng checkpoint mới nhất; thread
  im quá hạn → 0; thread có run `waiting_approval` → không mất gì; tenant B không bị
  chạm khi sweep chạy cho dữ liệu của A (lượt quét chéo tenant chỉ xóa theo điều kiện).
- Chứng minh đỏ cho từng dòng bảng "Quy tắc và kiểm soát", ghi dưới `## Comments`.
- `make ci` xanh; `make infra-down` cho repo này khi xong.

## Nguồn

- Audit harness 6/10/2026, khu `context-compaction`: gap no-op trong vòng tool, gap mất
  summary trên thread nhiều lượt, gap không có chủ cửa sổ, gap checkpoint phình
  (phần "offboarding/retention never touch the table" sai một nửa ở repo này: offboarding
  có xóa, qua catalog).
- `context_compaction.py:88-296`, `agent_factory.py:84-106`, `model/profiles.py:28-58`,
  `adapters/checkpoint.py:128-244`, `0001_platform_baseline.sql:366-398, 863-866`,
  `dw_platform/adapters/persistence/offboarding.py`, `dw_memory/retention.py`,
  `db/migrations/versions/0010_memory_retention_drain.py`.
- `failure-modes.md` #1, #3, #4, #6.

## Comments
