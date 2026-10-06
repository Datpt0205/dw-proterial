# 02 — Approval, run và audit đọc theo workspace; route nào cũng kiểm scope

Status: ready-for-agent
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
thành viên W2):

- [ ] B gọi `GET /approvals`: không có approval nào của W1. `GET /approvals/{id}` với id của
      W1: 404.
- [ ] B giữ `approvals.decide` ở W2 quyết approval của W1: 404; approval vẫn `pending`,
      không có dòng `approval_decisions`, run của W1 không chạy tiếp.
- [ ] A quyết approval của W1: run chạy tiếp với `workspace_id = W1` (khẳng định trên
      `RunContext` mà runner giả nhận).
- [ ] B gọi `GET /runs/{id}` với run của W1: 404. Người không có `runs.read`: 403.
- [ ] B gọi `GET /audit/events`: không có dòng nào của W1. Người chỉ có `approvals.read`
      (vai `member`): 403; người có `audit.events` (vai `director`): 200.
- [ ] Mutation, ghi vào Comments: bỏ điều kiện workspace ở `list_pending` thì ca đầu đỏ; bỏ
      `require` ở `GET /runs/{id}` thì ca 403 đỏ.
- [ ] Trang `/approvals` và `/audit` của web vẫn chạy với người có scope.
- [ ] `make ci` xanh; hợp đồng OpenAPI và client sinh lại nếu đổi.

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
