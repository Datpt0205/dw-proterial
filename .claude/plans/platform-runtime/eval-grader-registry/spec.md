# Bảng grader do composition root dựng, để context đăng ký grader của mình

Area: platform-runtime · Nhánh: `main` (worktree `codebase-main`) · Viết: 3/10/2026

Lát nền tảng, trung tính với sản phẩm. `CLAUDE.md` bước 5 đòi mỗi bounded context có eval
dataset với đủ ca an ninh và grader `<name>.<gate>`. Hôm nay grader chỉ đăng ký được bằng
cách sửa `dw_evals`, nên một context muốn grader riêng phải hoặc đặt code của mình vào
`dw_evals`, hoặc để `dw_evals` import context (cạnh ngược chiều). Đã kiểm trên code của
`main` ngày 3/10/2026.

## Mục tiêu

`run_dataset` dùng bảng grader được truyền vào. `scripts/run_evals.py` (composition root của
eval) dựng bảng từ grader nền tảng cộng grader của từng context, ở một seam có đánh dấu,
cùng khuôn với seam ở `apps/api/src/dw_api/bootstrap/wiring.py` và
`apps/worker/src/dw_worker/main.py`. `dw_evals` không import context nào (ticket 01).

## Hiện trạng (đã kiểm trong code)

- `packages/python/dw_evals/src/dw_evals/runner.py:16` import thẳng `GRADERS`; `_grade`
  (`runner.py:61`) tra `GRADERS.get(case.grader)`; `run_dataset(dataset, repo_root)`
  (`runner.py:72`) không nhận bảng nào. Tên không có trong bảng thì ca hỏng "unknown grader".
- `GRADERS` (`dw_evals/graders.py:215-220`) là dict cố định bốn grader nền tảng:
  `runtime.prompt_injection`, `runtime.side_effect_approval`,
  `knowledge.cross_tenant_rejected`, `memory.write_policy`.
- `scripts/run_evals.py:36` quét mọi `evals/datasets/*.json` khi `--smoke`, rồi gọi
  `run_dataset(dataset, REPO_ROOT)` (`:46`). `make eval-smoke` và `make ci` chạy lệnh này.
- `dw_evals/tests/unit/test_eval_runner.py:16, 28-33` cũng chạy mọi dataset trong
  `evals/datasets` qua `run_dataset` với bảng nền tảng. Dataset đầu tiên dùng grader của
  context sẽ làm test này đỏ với "unknown grader", dù script đúng.
- `scripts/new_context.py` không sinh eval dataset (docstring dòng 48-52) và chưa biết seam
  grader nào.

## Trong phạm vi

- Ticket 01: `run_dataset` nhận bảng grader; seam đăng ký ở `scripts/run_evals.py`; tên trùng
  thì dừng; test chạy mọi dataset dùng đúng bảng của script.

## Ngoài phạm vi

- Grader cụ thể của context nào: context tự viết trong package của mình.
- Đổi định dạng dataset hay luật `has_full_security_coverage`: giữ nguyên.

## Tiêu chí xong

- Ticket 01 `resolved`; `make ci` xanh; `lint-imports` xanh (không cạnh `dw_evals` → context).
- Mỗi kiểm soát mới có một test đã thấy đỏ khi gỡ kiểm soát (ghi trong Comments của ticket).

## Phụ thuộc

Không bị chặn bởi gì. Context đầu tiên cần grader riêng chờ ticket 01 trước eval dataset
của nó.

## Câu hỏi còn mở

1. **`CLAUDE.md` bước 5** ghi grader "in `dw_evals`". Sau ticket 01, grader của context nằm
   trong package của context và đăng ký ở seam của `scripts/run_evals.py`. Đề xuất: sửa câu
   đó trong cùng thay đổi (đây là đổi kiến trúc ghi lại, không lệch thầm lặng).

## Danh sách ticket

| #   | Ticket                                                                                                       | Status          | Blocked by |
| --- | ------------------------------------------------------------------------------------------------------------ | --------------- | ---------- |
| 01  | [`run_dataset` nhận bảng grader; seam đăng ký ở `run_evals.py`](issues/01-run-dataset-takes-grader-table.md) | ready-for-agent | —          |
