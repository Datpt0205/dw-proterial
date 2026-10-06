# 01 — Quyết định approval ghi `audit_events` cùng giao dịch

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Mỗi lần duyệt hay từ chối một approval để lại một dòng trong `platform.audit_events`, bảng
mà `dw_app` chỉ thêm được, không sửa, không xóa. Dòng đó ghi người quyết, ghi cùng giao
dịch với `approval_decisions`: không có quyết định nào thiếu vết, và không có vết nào cho
một quyết định đã rollback. Hôm nay người quyết chỉ nằm ở `approval_decisions`, bảng ứng
dụng sửa được, còn dòng `run.resumed` lại ghi người khởi chạy run (spec, Hiện trạng).

## Việc cần làm

- Trong `ApproveAndResumeService.decide` (`approval_flow.py`), cùng UoW với
  `uow.approvals.add_decision(decision)` và trước `uow.commit()`, gọi `uow.audit.append`
  với một `AuditEvent`:
    - `action = "approval.decided"`, `resource_type = "approval_request"`, `resource_id` là
      id của approval, `run_id` là run của approval (có thể không có);
    - `actor_id` là người quyết (`context.principal_id`), không phải người khởi chạy run;
    - `details` chỉ mang định danh và mã: `approval_type`, `outcome` (`approved`,
      `rejected`), `decision_id`, `withdrawn` (người yêu cầu tự rút ở loại không nghiêm).
      Không chép `comment` hay `payload`: hai thứ đó có thể mang dữ liệu nghiệp vụ, và người
      có quyền đọc ghi chú ở `approval_decisions`;
    - `occurred_at` bằng `decided_at` của quyết định.
- Migration mới (revision id hex ngẫu nhiên của alembic): thu UPDATE của `dw_app` trên
  `platform.approval_decisions`, vì một quyết định chỉ được ghi một lần và không code nào sửa
  nó. Giữ DELETE: lane offboarding xóa mọi bảng mà `dw_app` có DELETE
  (`offboarding.py:90-98`), còn dòng audit append-only là vết bền. Thêm khẳng định vào
  `packages/python/dw_platform/tests/integration/test_privileges.py`.

## Tiêu chí chấp nhận

- [ ] Integration (DB thật): duyệt một approval cho đúng một dòng `approval.decided`, có
      `actor_id` là người quyết, `details.outcome = approved`, cùng `decision_id` với dòng
      `approval_decisions`. Từ chối cho `outcome = rejected`. Người yêu cầu tự rút một loại
      không nghiêm cho `withdrawn = true`.
- [ ] Cùng giao dịch: `uow.audit.append` ném lỗi thì không có dòng `approval_decisions`,
      approval vẫn `pending`, run không chạy tiếp. Commit lỗi thì không có cả hai dòng.
- [ ] Quyết định bị từ chối trước khi ghi (thiếu scope, tách nhiệm, thiếu ghi chú ở loại
      nghiêm, run không chờ approval): không có dòng `approval.decided`.
- [ ] `details` không chứa `comment` hay khóa nào của `payload` (test so tập khóa).
- [ ] `dw_app` UPDATE `platform.approval_decisions` bị từ chối; INSERT, SELECT, DELETE vẫn
      được; test offboarding hiện có vẫn xanh (dòng của tenant được offboard vẫn bị xóa).
- [ ] Mutation, ghi vào Comments: bỏ lệnh `append` thì ca đầu đỏ; dời `append` ra sau
      `commit` thì ca "append ném lỗi" đỏ.
- [ ] `make ci` xanh.

## Nguồn

- `packages/python/dw_agent_runtime/src/dw_agent_runtime/approval_flow.py:96-182`.
- `packages/python/dw_platform/src/dw_platform/adapters/persistence/repositories.py:147-159`
  (`add_decision`), `:163` (`SqlAuditRepository`); `adapters/persistence/uow.py:61`
  (`uow.audit`).
- `packages/python/dw_agent_runtime/src/dw_agent_runtime/adapters/langgraph_runner.py:583`
  (`run.resumed`, người làm là `run_context.actor_id`).
- `db/migrations/sql/0001_platform_grants.sql:31-37`;
  `packages/python/dw_platform/src/dw_platform/adapters/persistence/offboarding.py:90-98`.
- `CLAUDE.md` "Side effects require policy evaluation, idempotency and audit", "Privileges
  are part of the schema"; `.claude/rules/failure-modes.md` #5.

## Comments
