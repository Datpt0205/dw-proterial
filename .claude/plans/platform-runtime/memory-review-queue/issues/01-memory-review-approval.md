# 01 — Candidate REVIEW thành approval `memory.review`; quyết định ghi hay bỏ qua đường ghi đã kiểm

Status: ready-for-agent
Blocked by: platform-runtime/approval-audit-and-workspace 01, 02; platform-runtime/memory-write-trust 01
Area: platform-runtime

## Mục tiêu

Mỗi candidate mà policy giữ lại để duyệt xuất hiện trong hộp approval chung; duyệt thì ghi
đúng một item qua đường ghi đã kiểm, từ chối thì không ghi gì, và cả hai có audit. Spec,
mục "Thiết kế", "Điểm dừng" và "Quy tắc và kiểm soát".

## Việc cần làm

1. `dw_memory/service.py`:
    - Nhánh REVIEW của `propose`: trong cùng giao dịch, chèn `platform.approval_requests`
      như spec mục Thiết kế 1. `dw_memory` không import adapter của `dw_platform`: dùng
      port approval mà service đã có quyền dùng, hoặc một Protocol hẹp do `dw_memory` khai
      và composition root thỏa (`CLAUDE.md`, "Independent bounded contexts").
    - Tách phần "kiểm bằng chứng → chèn item → supersession → item_evidence" của
      `propose` thành một hàm dùng chung. `promote(candidate_id, decided_by, context)`
      đọc dòng candidate dưới RLS, dựng item từ nó, gọi hàm đó, đặt
      `write_candidates.memory_id`, ghi audit `memory.written_after_review`. Đã có
      `memory_id` thì trả kết quả cũ (idempotent).
    - `reject(candidate_id, decided_by, context)`: chỉ audit `memory.review_rejected`.
2. `dw_agent_runtime/approval_flow.py`, `decide`: với approval không có run, thêm
   `uow.outbox.add(...)` event `f"{request.approval_type}.decided"` trước `uow.commit()`.
   Không nhánh theo loại approval.
3. Kiểm clearance khi quyết `memory.review`: người quyết phải đọc được phân loại trong
   payload (thang ở `dw_knowledge/contracts.py`, không chép). Đặt kiểm ở chỗ quyết định
   xảy ra; nếu `decide` không nên biết memory, đó là một Protocol "điều kiện quyết theo
   loại" đăng ký ở composition root, cùng kiểu `strict_approval_prefixes`.
4. `apps/worker/src/dw_worker/consumers/memory.py` + `main.py`: handler
   `memory.review.decided` gọi `promote` hoặc `reject`; tenancy lấy từ envelope, không từ
   payload; bằng chứng hết hợp lệ → audit `memory.review_failed` +
   `UndeliverableEventError`.
5. `apps/api/src/dw_api/routes/v1/memory.py`: `GET /memory/candidates/{id}` trả nội dung
   candidate cho người có `memory.read` và đủ clearance; payload approval chỉ mang định
   danh. Cập nhật `contracts/openapi` bằng `scripts/generate_contracts.py`.
6. Nếu chạm Điểm dừng của spec: dừng, ghi khoảng trống vào `## Comments`, để
   `Status: needs-info`, và không commit code nửa vời.

## Tiêu chí chấp nhận

- Test (integration, Postgres thật):
    - candidate REVIEW → đúng một approval `memory.review` pending, `run_id` NULL, payload
      không có `content`;
    - duyệt → đúng một `memory.items`, có `item_evidence`, audit; giao event
      `memory.review.decided` lần hai → vẫn một item;
    - từ chối → 0 item, audit `memory.review_rejected`;
    - duyệt khi chunk được trích đã bị xóa → 0 item, audit `memory.review_failed`;
    - người của tenant B gọi quyết approval của tenant A → `NotFoundError` (RLS), 0 item;
    - người clearance `internal` duyệt candidate `restricted` → bị từ chối, approval vẫn
      pending;
    - nếu `memory.` là strict: người có run sinh fact tự duyệt → bị từ chối.
- Chứng minh đỏ cho từng dòng của bảng "Quy tắc và kiểm soát", ghi dưới `## Comments`.
- `make ci` xanh; `make infra-down` cho repo này khi xong.

## Nguồn

- Audit harness 6/10/2026: `memory-store` gap "REVIEW decisions land in
  memory.write_candidates and nothing reads them", `file-memory-and-instructions` gap
  "REVIEW-held memories have no path to a human", `reuse` gap "The long-term memory loop is
  open at both ends".
- `dw_memory/policy.py:45-60`, `dw_memory/service.py:132-264`,
  `dw_agent_runtime/approval_flow.py`, `dw_platform/application/ports.py:236-315`,
  `apps/worker/src/dw_worker/consumers/outbox.py`, `apps/api/src/dw_api/routes/v1/approvals.py`,
  `apps/api/src/dw_api/routes/v1/memory.py`.
- `CLAUDE.md` "Human-in-command", "Side effects require policy evaluation, idempotency and
  audit"; `failure-modes.md` #1, #5.

## Comments
