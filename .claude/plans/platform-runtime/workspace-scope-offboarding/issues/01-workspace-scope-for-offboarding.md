# 01 — Lane offboarding gắn `app.workspace_scope`; guard RLS nhận nó chỉ cùng vế tenant

Status: resolved
Blocked by: —
Area: platform-runtime

## Mục tiêu

Một context có RLS lọc tenant và workspace được lane offboarding xuất đủ và xóa đủ,
và `test_rls_coverage.py` giữ setting mở rộng không vượt tenant. Spec, mục "Dạng
policy" và "Quy tắc và kiểm soát".

Hôm nay `test_every_policy_actually_consults_the_tenant_setting` coi một policy là
đã thu hẹp ngay khi biểu thức có chuỗi `current_setting('app.tenant_id'` ở bất kỳ
đâu (`test_rls_coverage.py:93-97, 211-212`). Policy
`tenant_id = … OR current_setting('app.workspace_scope', true) = 'tenant'` vì vậy
xanh, trong khi nó mở mọi tenant cho bất kỳ giao dịch nào gắn setting đó.

## Việc cần làm

1. `packages/python/dw_platform/src/dw_platform/adapters/persistence/offboarding.py`:
    - `export_rows` và `purge_rows` gắn `app.workspace_scope = 'tenant'` cùng
      `app.tenant_id`, bằng `set_config(..., true)`, trước truy vấn bảng đầu tiên của
      giao dịch. Gộp vào một câu như `tenant_session.py:23-27` hay hai câu đều được;
      `claim_requested`, `mark_status` không đổi.
    - Docstring của module: vì sao (bảng lọc theo workspace đọc 0 dòng dưới riêng
      `app.tenant_id`, rồi CASCADE từ `platform.workspaces` xóa mất), và đây là chỗ
      duy nhất gắn setting này.
2. `packages/python/dw_platform/tests/integration/test_rls_coverage.py`:
    - Thêm một hằng riêng cho setting mở rộng (`current_setting('app.workspace_scope'`),
      tách hẳn khỏi `_TRUSTED_SETTINGS`: setting mở rộng không bao giờ tính là thu hẹp.
      `app.worker_drain` giữ nguyên chỗ cũ (policy của nó cố ý không có vế tenant).
    - Luật 1: với mỗi policy mà `qual` hay `with_check` đọc setting mở rộng, biểu thức
      ở mức ngoài cùng phải là một AND có một vế đọc `app.tenant_id`, và setting mở
      rộng chỉ nằm trong vế khác. Sai thì đỏ, nêu tên policy. Postgres in
      `pg_policies.qual` với ngoặc đầy đủ, nên tách vế AND ở độ sâu ngoặc thứ nhất là
      đủ; in thử biểu thức thật trước khi dựa vào dạng đó (`failure-modes.md` #4).
    - Luật 2: bảng có policy đọc `app.workspace_id` mà không policy nào của nó đọc
      `app.workspace_scope` thì đỏ, nêu tên bảng: lane offboarding không thấy dòng của
      bảng đó.
    - Docstring của hai test: vì sao, và rằng chúng áp cho mọi schema dò từ catalog.
3. `packages/python/dw_platform/tests/integration/test_offboarding.py`, với một bảng
   thử lọc theo workspace:
    - Tạo trong fixture bằng phiên migrator: cột `tenant_id`, `workspace_id`; policy
      `tenant_isolation_<…>` đúng dạng của spec cho `USING` và `WITH CHECK`; `ENABLE` và
      `FORCE`; grant `SELECT`, `DELETE` cho `dw_app` (và `USAGE` nếu ở schema riêng).
      Xóa ở teardown. `db_urls` dùng chung cả phiên test, nên trong lúc tồn tại bảng
      thử phải qua mọi guard của `test_rls_coverage.py`, `test_privileges.py`, và xóa
      xong không để lại gì (`failure-modes.md` #3: hai tệp tranh nhau một dòng).
    - Dữ liệu: hai workspace của tenant A, một workspace của tenant B, mỗi workspace
      một dòng.
    - `export_rows(A)` có dòng của cả hai workspace của A, không dòng nào của B.
    - `purge_rows(A)` để lại 0 dòng của A trong bảng thử; dòng của B còn nguyên.
    - Giao dịch `dw_app` gắn `app.tenant_id` = B và `app.workspace_scope = 'tenant'`
      đọc 0 dòng của A.
    - Không dư setting: với một engine giữ đúng một kết nối, sau `export_rows`, giao
      dịch kế tiếp đọc `current_setting('app.workspace_scope', true)` ra rỗng.
4. Kiểm `platform.notifications` có cùng bẫy không: policy
   `tenant_isolation_notifications_*` đọc `app.tenant_id` và `app.user_id`
   (`db/migrations/versions/855ae928c3fa_platform_in_app_notifications.py:44-47,
96-103`), nên dưới giao dịch của lane có thể nó đọc 0 dòng, rồi dòng mất theo
   CASCADE khi chưa xuất. Đo trên DB test, ghi kết quả vào Comments; có bẫy thì ghi
   vào `.claude/plans/ops-hardening.md` mục Open, không sửa ở ticket này. Luật 2 không
   bắt trường hợp này vì nó không đọc `app.workspace_id`.
5. `CLAUDE.md` mục "Tenancy and authorization": một dòng: bảng lọc theo workspace dùng
   dạng `tenant AND (workspace OR app.workspace_scope = 'tenant')`; chỉ lane
   offboarding gắn `app.workspace_scope`, theo giao dịch; `test_rls_coverage.py`
   giữ cả hai.

## Tiêu chí chấp nhận

- `uv run pytest packages/python/dw_platform/tests/integration -m integration` xanh;
  `make ci` xanh.
- Chứng minh đỏ, ghi lệnh và kết quả dưới `## Comments`:
    - bỏ dòng gắn `app.workspace_scope` ở `export_rows` → test xuất đỏ; ở `purge_rows`
      → test xóa đỏ;
    - đổi tham số cuối của `set_config` thành `false` → test không dư setting đỏ;
    - bỏ vế tenant khỏi policy của bảng thử → test "không vượt tenant" đỏ;
    - policy thử `tenant OR scope`, và `(tenant AND workspace) OR scope` (thiếu ngoặc) →
      luật 1 đỏ, nêu đúng tên policy; dạng của spec → xanh;
    - bảng thử chỉ có policy `tenant AND workspace` → luật 2 đỏ, nêu đúng tên bảng.
- `rg "set_config\('app.workspace_scope'" packages apps` (bỏ thư mục `tests/`) chỉ ra
  `offboarding.py`.
- Không tên sản phẩm hay tên context nào trong các tệp đã sửa.

## Nguồn

- Spec của lát này: "Dạng policy", "Quy tắc và kiểm soát", "Câu hỏi còn mở".
- `offboarding.py:12-18, 39, 53-71, 147-179` (chỉ gắn `app.tenant_id`; dò bảng theo
  `tenant_isolation_%` và quyền của `dw_app`).
- `test_rls_coverage.py:86-97, 194-228` (setting tin cậy; một policy xanh ngay khi
  có chuỗi `app.tenant_id`).
- `tenant_session.py:23-27` (`set_config(..., true)` theo giao dịch).
- `test_offboarding.py` (mỗi test seed tenant riêng; `db_urls` dùng chung cả phiên).
- `db/migrations/sql/0001_platform_grants.sql:31-32` (`dw_app` có DELETE trên mọi
  bảng `platform`, gồm `workspaces`).
- `CLAUDE.md` "Tenancy and authorization", "A second language" (gắn setting theo
  giao dịch bằng `set_config(..., true)`).
- `.claude/rules/failure-modes.md` #0, #3, #4, #5, #7.

## Comments

- 2026-10-03, làm xong trên `main`.
    - `offboarding.py`: `export_rows`, `purge_rows` gắn `app.tenant_id` và
      `app.workspace_scope = 'tenant'` trong một câu `set_config(..., true)`
      (`_SET_TENANT_ALL_WORKSPACES`); `mark_status` giữ `_SET_TENANT`.
    - `test_rls_coverage.py`: luật 1 (`scope_outside_a_tenant_clause`) và luật 2
      (`workspace_tables_blind_to_scope`), hàm thuần trên `pg_policies`, áp cho mọi
      schema dò từ catalog. Đo trước trên Postgres 16: biểu thức policy luôn in
      đủ ngoặc (`a AND b OR c` thành `((a AND b) OR c)`). Thêm
      `test_the_scope_rules_catch_the_wrong_shapes`: tạo trong một giao dịch rồi
      rollback các policy thật dạng `tenant OR scope`, thiếu ngoặc, vế tenant nới
      bằng scope, vế tenant nới bằng thứ khác, scope đứng một mình, `WITH CHECK`
      sai, và một bảng chỉ lọc `tenant AND workspace`; khẳng định hai luật bắt
      đúng tên policy, tên bảng, và tha dạng của spec. Đây là chứng minh đỏ thường
      trực của hai luật, vì hôm nay chưa bảng nào lọc theo workspace.
    - `test_offboarding.py`: bảng thử `offboarding_ws_probe.rows` dựng và xóa trong
      fixture; bốn test (xuất đủ hai workspace, xóa đủ và để nguyên tenant khác,
      scope không vượt tenant, scope hết theo giao dịch trên một kết nối dùng lại,
      có kiểm `pg_backend_pid` để chắc là cùng kết nối).
    - Chứng minh đỏ (đột biến tự động, mỗi lần hoàn nguyên; tám trên tám đỏ):
      bỏ scope ở `export_rows` → `assert set() == {'a1', 'a2'}`; ở `purge_rows` →
      `assert {'a1', 'a2'} == set()`; `set_config(..., false)` → "the next
      transaction inherited app.workspace_scope='tenant'"; bỏ vế tenant của policy
      bảng thử → `{'a1', 'a2', 'b1'} == {'b1'}`; luật 1 nhận OR ở mức ngoài, nhận OR
      trong vế tenant, chỉ đọc `USING`; luật 2 không thấy gì → test dạng sai đỏ.
      Lần đầu, đột biến "nhận OR trong vế tenant" còn xanh vì không dạng thử nào
      chỉ điều kiện đó bắt; thêm dạng `loose_tenant` thì đỏ.
    - Bước 4, đo trên DB test: một tenant có một thông báo, `export_rows` liệt kê
      `platform.notifications` với 0 dòng, sau `purge_rows` còn 0 thông báo (mất
      theo CASCADE từ `workspaces`). Có bẫy; ghi ở `ops-hardening.md` Open, không
      sửa ở đây.
    - Bước 5: một dòng ở `CLAUDE.md` "Tenancy and authorization".
