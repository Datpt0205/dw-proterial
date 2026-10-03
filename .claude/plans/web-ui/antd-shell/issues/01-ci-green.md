# 01 — CI xanh trên `main`

Status: resolved
Blocked by: —
Area: web-ui

## Mục tiêu

`main` có CI xanh trước khi lát shell bắt đầu, để một bước đỏ sau đó là của lát này,
không phải của nợ cũ.

## Việc cần làm

- Bước quét bí mật (gitleaks v8.24.3, toàn lịch sử) đỏ từ `8c46c65`: chú thích trong
  `.gitleaksignore` trích nguyên cụm từ bị nhận nhầm, nên luật `generic-api-key` bắt
  luôn chú thích đó. Đổi chú thích thành lời tả, thêm một dấu vân tay cho commit còn
  mang câu trích. Không có bí mật nào liên quan.
- Ba test LISTEN/NOTIFY trong `test_run_state_announcements.py` hết giờ trong CI:
  plugin anyio và pytest-asyncio tranh nhau bọc fixture async. Chỉ giữ pytest-asyncio;
  bỏ `pytest.mark.anyio` và fixture `anyio_backend` ở bốn module integration và một
  test unit; `addopts` tắt plugin anyio.

## Tiêu chí chấp nhận

- [x] gitleaks cùng phiên bản: 1 phát hiện trên `origin/main` trước, 0 sau.
- [x] Ép plugin anyio nạp sau pytest-asyncio (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, rồi
      `-p pytest_asyncio.plugin -p anyio.pytest_plugin`): 3 đỏ trước, 4 xanh sau; nạp
      mặc định: 4 xanh.
- [x] `pytest.mark.anyio` mới làm lỗi lúc thu thập test dưới `--strict-markers`.
- [x] `dw_agent_runtime` integration 48/48, Qdrant ranker 5/5, rate-limit unit 2/2.

## Nguồn

- Commit `4e8100d` fix(ci): gitleaks matched its own ignore file's comment.
- Commit `8312479` fix(test): one async test runner.
- `.claude/plans/platform-runtime.md` (ghi lại việc điều tra hết giờ).

## Comments
