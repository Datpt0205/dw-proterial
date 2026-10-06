# 02 — Approval, run và audit đọc theo workspace; route nào cũng kiểm scope

Status: resolved
Blocked by: —
Area: platform-runtime

## Mục tiêu

Một thành viên chỉ thấy approval, run và audit của workspace mình, và mỗi route đọc kiểm
đúng scope của nó. Hôm nay RLS của ba bảng chỉ lọc tenant, nên thành viên của một workspace
đọc được payload approval, kết quả run và chi tiết audit của mọi workspace khác trong tenant;
`GET /runs/{id}` không kiểm scope nào; route audit kiểm `approvals.read` (vai `member` có)
thay vì `audit.events` (spec, Hiện trạng). Một context đặt dữ liệu nghiệp vụ vào payload,
kết quả run hay chi tiết audit sẽ lộ nó cho cả tenant.

## Việc cần làm

- Approval:
    - `list_pending` lọc `workspace_id` của người gọi (lấy từ `AccessContext`, không từ
      client); fingerprint của cursor mang workspace như đã mang tenant;
    - `get` theo id (dùng ở `GET /approvals/{id}` và ở `decide`) lọc cùng workspace; approval
      của workspace khác là 404, không phải 403;
    - run chạy tiếp lấy `workspace_id` của run (cột `workspace_id` của `worker_runs`, ghi ở
      `run_store.py:354`), không của người quyết (`approval_flow.py:151`). `RunRecord`
      (`run_store.py:70-103`) chưa mang cột này: thêm trường và đọc nó ở `get`. Sửa chú thích
      sai ở `approval_flow.py:118-119`.
- `GET /runs/{run_id}`: `authorization.require(action="runs.read", ...)` như
  `get_timeline`; `run_store.get` lọc workspace của người gọi, run của workspace khác là 404.
- `GET /audit/events`: kiểm `audit.events`, không kiểm `approvals.read`; chỉ trả dòng của
  workspace người gọi.
- Không đổi policy RLS ở ticket này (spec, Ngoài phạm vi): lọc ở repository, có test âm.

## Tiêu chí chấp nhận

Integration (`apps/api`, DB thật; một tenant, hai workspace W1, W2; A là thành viên W1, B là
thành viên W2): _(`apps/api` không có suite integration; test DB thật nằm ở
`dw_platform/tests/integration/test_workspace_reads.py` và
`dw_agent_runtime/tests/integration/test_approval_workspace.py`; 403/404 của route ở test unit
`apps/api/tests/unit/test_run_and_audit_reads.py` và `test_approvals_endpoint.py`.)_

- [x] B gọi `GET /approvals`: không có approval nào của W1. `GET /approvals/{id}` với id của
      W1: 404.
- [x] B giữ `approvals.decide` ở W2 quyết approval của W1: 404; approval vẫn `pending`,
      không có dòng `approval_decisions`, run của W1 không chạy tiếp.
- [x] A quyết approval của W1: run chạy tiếp với `workspace_id = W1` (khẳng định trên
      `RunContext` mà runner giả nhận).
- [x] B gọi `GET /runs/{id}` với run của W1: 404. Người không có `runs.read`: 403.
- [x] B gọi `GET /audit/events`: không có dòng nào của W1. Người chỉ có `approvals.read`
      (vai `member`): 403; người có `audit.events` (vai `director`): 200.
- [x] Mutation, ghi vào Comments: bỏ điều kiện workspace ở `list_pending` thì ca đầu đỏ; bỏ
      `require` ở `GET /runs/{id}` thì ca 403 đỏ.
- [x] Trang `/approvals` và `/audit` của web vẫn chạy với người có scope. _(Xem trong trình duyệt ở repo sản phẩm, 6/10/2026; ở đây chỉ vitest:
      `home-page`, `session-chip`, `approvals-page`.)_
- [x] `make ci` xanh; hợp đồng OpenAPI và client sinh lại nếu đổi.

## Nguồn

- `apps/api/src/dw_api/routes/v1/approvals.py:44-105`, `runs.py:41-58`, `audit.py:39-72`.
- `packages/python/dw_platform/src/dw_platform/adapters/persistence/repositories.py:98-145`
  (`get`, `list_pending`); `packages/python/dw_agent_runtime/src/dw_agent_runtime/approval_flow.py:118-119, 151`;
  `packages/python/dw_agent_runtime/src/dw_agent_runtime/adapters/run_store.py:70-103, 354, 412-418`.
- `db/migrations/sql/0001_platform_baseline.sql:839, 842, 875` (policy chỉ lọc tenant);
  `db/migrations/sql/0001_platform_reference.sql:68, 74` (`audit.events`).
- `CLAUDE.md` "Tenancy and authorization" (test âm chéo tenant và chéo workspace là bắt
  buộc; ẩn nút không phải phân quyền).

## Comments

### 2026-10-06: đã làm (đưa ngược từ repo sản phẩm đầu tiên)

Làm ở repo sản phẩm (commit `7b411df` ở đó, cùng hai vòng review), đưa về đây nguyên hành
vi, bỏ phần của sản phẩm. Nhánh `feat/upstream-elmich-platform`.

- Lọc ở repository, RLS không đổi (vẫn chỉ tenant). `workspace_id` là tham số keyword
  BẮT BUỘC, không mặc định: `ApprovalRepositoryPort.get/list_pending`,
  `AuditRepositoryPort.list_page/list_for_run`, `SqlPendingApprovalQuery`,
  `SqlWorkerRunStore.get` (workspace của `RunContext`), `thread_belongs_to(tenant,
workspace, thread)`. Người gọi truyền `context.workspace_id` của `AccessContext`.
  Workspace khác trả như không tồn tại (404 ở route).
- `decide` đọc approval và run trong workspace người quyết; resume với
  `RunRecord.workspace_id` (đọc từ dòng `worker_runs`). `settle_review` của `dw_memory`
  (`memory.review`) đọc approval với workspace của context đến từ event, như đã so
  `request.workspace_id` sau đó.
- `GET /runs/{id}` kiểm `runs.read`; `GET /audit/events` kiểm `audit.events`. Fingerprint
  cursor của `approvals.pending` và `audit.events` mang `workspace`.
- Migration `6d4aed20ccf2`: `ix_approval_requests_page` thành `(tenant_id, workspace_id,
status, created_at DESC, id DESC)`; `ix_audit_events_page (tenant_id, workspace_id,
occurred_at DESC, id DESC)` trên bảng cha phân vùng. Docstring ghi khóa SHARE lúc dựng
  và cách làm không chặn ghi khi đã có trail lớn.
- Web: mục `/audit` của nav registry và link trong menu tài khoản đọc cùng scope
  `audit.events` (một chủ). Vitest `home-page.test.tsx`, `session-chip.test.tsx`.
- Test và mutation (ở repo này): bỏ điều kiện workspace ở `list_pending` thì 2 test đỏ, ở
  `approvals.get` thì 3 test đỏ, ở `run_store.get` thì đỏ, bỏ `require(runs.read)` thì đỏ, route audit về
  `approvals.read` thì đỏ, fingerprint không workspace thì đỏ. `decide` resume với
  `context.workspace_id` thay vì của run **vẫn xanh**, như ở repo sản phẩm: sau hai lần
  đọc đã lọc, hai giá trị luôn bằng nhau; đọc từ run là để giá trị có một nguồn, lệch được
  chặn trước đó (`test_a_run_in_another_workspace_than_its_approval_is_not_resumed`).
- Còn mở: liệu UoW nên giữ workspace (một chủ) thay vì tham số đọc (review vòng 1 ở repo
  sản phẩm, phát hiện 4); trang `/audit` thiếu scope vẫn hiện lỗi API của trang shadcn,
  chưa phải `Result 403`.
