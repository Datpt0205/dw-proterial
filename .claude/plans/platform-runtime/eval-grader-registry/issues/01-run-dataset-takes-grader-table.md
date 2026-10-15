# 01 — `run_dataset` nhận bảng grader; seam đăng ký ở `run_evals.py`

Status: done (2026-10-12; code from commit `5643634`, 7/10/2026; adversarial review 2026-10-12, one test tightened, committed in `dd5ef1d`)
Blocked by: —
Area: platform-runtime

## Mục tiêu

Một bounded context đăng ký grader của mình mà không sửa `dw_evals` và không để `dw_evals`
import nó. Bảng grader có một chủ: hàm dựng bảng ở `scripts/run_evals.py`; script và test
chạy mọi dataset cùng đọc hàm đó (spec, Hiện trạng).

## Việc cần làm

1. `dw_evals/runner.py`: `run_dataset(dataset, repo_root, graders: Mapping[str, Grader])`;
   `_grade` tra trong `graders`, không import `GRADERS` nữa (bỏ import ở `runner.py:16`).
   Không có giá trị mặc định: một lời gọi quên bảng là lỗi kiểu, không phải bảng rỗng chạy
   lặng lẽ (failure-modes #7).
2. `scripts/run_evals.py`: hàm `grader_table() -> dict[str, Grader]` bắt đầu từ `GRADERS` của
   nền tảng, rồi gộp bảng của từng context ở một chỗ đánh dấu
   `# --- BOUNDED CONTEXT GRADERS REGISTER HERE ---`, cùng khuôn với seam ở `wiring.py` và
   `dw_worker/main.py`. Gộp qua một hàm `merge_graders(*tables)` ném lỗi khi hai bảng trùng
   tên, kèm tên trùng; script dừng với mã khác 0. `main()` gọi `run_dataset(dataset,
REPO_ROOT, grader_table())`.
3. Test chạy mọi dataset (`test_eval_runner.py:28-33`) phải dùng đúng bảng của script, không
   bảng nền tảng: chuyển nó sang `apps/api/tests/unit/` (package đã phụ thuộc mọi context và
   đã nạp script bằng `importlib.util.spec_from_file_location`, như
   `test_release_manifest.py`), gọi `grader_table()`. Test còn lại trong `dw_evals` truyền
   `GRADERS` tường minh.
4. `scripts/new_context.py`: thêm seam này vào danh sách chỗ nó vá (dòng import và lời gọi
   đăng ký, viết dạng comment như lane worker nếu context mới chưa có grader), cập nhật
   `CLAUDE.md` "Adding a bounded context" và job `scaffold-smoke` cho khớp. Không sinh
   grader hay dataset (docstring dòng 48-52 giữ nguyên lý do).

## Tiêu chí chấp nhận

- [x] Unit: `run_dataset` với một bảng chỉ có grader giả `x.ok` chấm ca dùng `x.ok` là đạt,
      và ca dùng `runtime.prompt_injection` là "unknown grader" (bảng truyền vào là bảng
      duy nhất được dùng). Đổi `_grade` về đọc `GRADERS` thì test đỏ.
- [x] Unit: `merge_graders` với hai bảng cùng có một tên ném lỗi nêu tên đó; gỡ kiểm trùng
      thì test đỏ.
- [x] `uv run python scripts/run_evals.py --smoke` vẫn xanh với `platform@1.0.0.json`, báo
      "security coverage ok".
- [x] Test chạy mọi dataset ở `apps/api/tests/unit/` xanh, và đỏ khi một dataset dùng tên
      grader không có trong `grader_table()`.
- [x] `lint-imports` xanh; `rg GRADERS packages/python/dw_evals/src` chỉ ra `graders.py`.
- [x] `make ci` xanh; job `scaffold-smoke` xanh với seam mới.

## Nguồn

- `packages/python/dw_evals/src/dw_evals/runner.py:16, 61, 72`;
  `packages/python/dw_evals/src/dw_evals/graders.py:57` (`Grader`), `:215-220` (`GRADERS`).
- `scripts/run_evals.py:36` (glob `evals/datasets/*.json`), `:46` (`run_dataset`).
- `packages/python/dw_evals/tests/unit/test_eval_runner.py:16, 28-33`;
  `apps/api/tests/unit/test_release_manifest.py:17` (nạp script).
- `scripts/new_context.py:48-52`; `CLAUDE.md` "Adding a bounded context" bước 5.
- `.claude/rules/failure-modes.md` #2 (một bảng, một chủ), #7.

## Comments

**Agent, 2026-10-12 — đóng: đã làm sẵn, không làm lại.** Toàn bộ ticket đã vào `main`
ở commit `5643634` ("context graders registered from the eval composition root", 7/10/2026),
mang lên từ sản phẩm đầu tiên cùng đợt merge `33658ac`. Code ở đâu:

- `packages/python/dw_evals/src/dw_evals/runner.py`: `run_dataset(dataset, repo_root, graders)`
  không có mặc định; `_grade` chỉ tra `graders`. `rg GRADERS packages/python/dw_evals/src`
  chỉ ra `graders.py:218`.
- `packages/python/dw_evals/src/dw_evals/graders.py:229` `merge_graders(*tables)` ném
  `ValueError` nêu tên trùng.
- `scripts/run_evals.py` `grader_table()`: `GRADERS` nền tảng, seam
  `# ---- BOUNDED CONTEXT GRADERS REGISTER HERE ----`, bảng `dw_sales.evals.GRADERS` đã đăng ký;
  `main()` gọi `run_dataset(dataset, REPO_ROOT, graders)`.
- `apps/api/tests/unit/test_eval_datasets.py`: chạy mọi dataset với `grader_table()` của script,
  nạp bằng `spec_from_file_location`. `dw_evals/tests/unit/test_eval_runner.py` truyền `GRADERS`
  tường minh và có hai test bảng giả `x.ok` / `merge_graders`.
- `scripts/new_context.py` `_patch_run_evals` (dòng 695) vá seam dạng comment; `CLAUDE.md` bước 5
  và comment job `scaffold-smoke` đã cập nhật (câu hỏi mở 1 của spec đã đóng trong cùng commit).
- Import-linter: hợp đồng "Platform does not import contexts" (có `dw_evals`) KEPT.

Xác minh 12/10/2026 trên `main` (8ac3d33, cây sạch phần này): ruff check, ruff format --check,
mypy (540 file), lint-imports (11 kept), verify_architecture, verify_invariants,
release_manifest --check đều xanh; unit `2383 passed, 3 skipped`; `run_evals.py --smoke`:
`platform_smoke@1.2.0` 4/4 và `sales@1.0.0` 10/10, cả hai "security coverage ok" (tiêu chí
ghi `platform@1.0.0`; dataset nền tảng nay là `platform@1.2.0`). CI `38221943428` (ab751f8)
xanh cả job `scaffold-smoke` ("A generated bounded context still plugs in"). Không chạy
scaffold-smoke cục bộ: nó sinh context vào cây làm việc đang có hai agent khác dùng.

Đột biến (sửa bằng bash trên nền xanh, thấy đỏ, khôi phục, `git diff` rỗng):

1. `_grade` tra `GRADERS` thay vì `graders` → `test_the_table_passed_in_is_the_only_one_consulted`
   đỏ (`x.ok` thành "unknown grader").
2. Bỏ kiểm trùng trong `merge_graders` (`if False and clash`) →
   `test_merge_graders_refuses_a_name_two_tables_claim` đỏ.
3. `grader_table()` bỏ `tables.append(SALES_GRADERS)` → `test_smoke_dataset_passes[sales@1.0.0]`
   đỏ ("unknown grader"), và `run_evals.py --smoke` báo `[FAIL] sales@1.0.0 0/10`, exit 1.
4. Đăng ký `SALES_GRADERS` hai lần → `run_evals.py --smoke` dừng `ValueError: grader names
registered twice: ['sales.extraction_accuracy', ...]`, exit 1.

Lệch còn lại, ngoài phạm vi ticket này (ghi lại, không sửa): `CLAUDE.md` bước 5 và comment do
`new_context.py` sinh nói grader nằm ở `dw_<name>.testing` (`testing.eval_graders`), còn DW1 đặt
ở `dw_sales.evals` (ticket sales 09). Nên thống nhất một chỗ — hoặc dời grader DW1, hoặc sửa
câu ở `CLAUDE.md` và template — trong một thay đổi riêng.

**Adversarial review, 2026-10-12 — one defect fixed, ticket done.** I re-ran the mutations myself
against a green baseline, each restored from a backup with `git diff` empty afterwards:

1. `_grade` falls back to the platform table (`{**GRADERS, **graders}`) →
   `test_the_table_passed_in_is_the_only_one_consulted` red.
2. `merge_graders` `if False and clash` → `test_merge_graders_refuses_a_name_two_tables_claim` red.
3. `grader_table()` drops `tables.append(SALES_GRADERS)` → `test_smoke_dataset_passes[sales@1.0.0]`
   red with 11× "unknown grader", and `run_evals.py --smoke` `[FAIL] sales@1.0.0 0/10`, exit 1.
4. **Fail-open**: an unknown grader returns `GradeResult.ok(reason="unknown grader")`. The
   `dw_evals` tests went red, but `apps/api/.../test_eval_datasets.py::test_a_grader_name_the_table_lacks_fails_its_case`
   stayed **green**: it asserted only the `reason` string, never that the case failed, so it could
   not catch a runner that passes the ticket's own scenario (acceptance 4, failure-modes #3).
   Fixed: it now asserts `not passed` and `not report.ok` too. With mutation 4 applied it is red
   (`passed=True`); restored, green.

Other findings:

- `scripts/new_context.py` and `scripts/run_evals.py` are byte-identical to `ab751f8`, whose CI
  `scaffold-smoke` was green, so that run covers the seam as it stands. `scripts/` is in mypy's
  `files`, so the "no default → type error" guard is actually checked.
- `uv export --package dw-api` / `dw-worker` list no `dw-evals`: an eval-only package stays out
  of the images.
- During the review the sales dataset was briefly red because another agent was renaming
  `sales_order_rules@1.0.0` → `1.1.0`. That was not a defect in this ticket; it was green again
  before the final run.
- `sales/dw1-portal-demo/issues/09` line 64 still says `compose_graders`; the function is
  `merge_graders`. A sales file, so I left it alone.

## As built

- `dw_evals.runner.run_dataset(dataset, repo_root, graders)` takes no default; `_grade` reads
  only `graders`, and a name missing from the table fails its case ("unknown grader").
- `dw_evals.graders.merge_graders(*tables)` refuses, by name, a grader that two tables both
  register. The platform's own `GRADERS` stays in `graders.py` and is the only `GRADERS` under
  `dw_evals/src`.
- `scripts/run_evals.py` `grader_table()` is the one seam
  (`# ---- BOUNDED CONTEXT GRADERS REGISTER HERE ----`). It already registers
  `dw_sales.evals.GRADERS`, and `main()` grades every dataset with it.
- `apps/api/tests/unit/test_eval_datasets.py` runs every dataset with the script's own table and
  shows that an unregistered name fails its case (tightened in this review).
  `dw_evals/tests/unit/test_eval_runner.py` passes `GRADERS` explicitly and has the `x.ok` and
  `merge_graders` tests.
- `scripts/new_context.py` `_patch_run_evals` writes the commented seam into the script. CLAUDE.md
  step 5 and the `scaffold-smoke` comment both describe it. "Platform does not import contexts"
  (with `dw_evals`) is KEPT.
- Acceptance "`make ci` green" was met by running each gate separately (list in the report),
  plus CI `38221943428` for `scaffold-smoke`. `make ci` was not run as one target.
- Still open, outside this ticket: where a context keeps its graders. CLAUDE.md step 5 and the
  generator say `dw_<name>.testing`, but DW1 uses `dw_sales.evals` (see the previous comment).
