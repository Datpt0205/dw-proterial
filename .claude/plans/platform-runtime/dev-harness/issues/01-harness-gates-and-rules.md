# 01 — Cổng commit cho mọi dạng commit, Stop hook theo phiên, plugin và rules nói đúng

Status: ready-for-agent
Blocked by: —
Area: platform-runtime

## Mục tiêu

Các cổng của harness gác đúng cái chúng nói là gác, trên Windows lẫn Linux, và tài liệu
của harness nói đúng điều đang chạy. Spec, mục "Quy tắc và quyết định" và "Quy tắc và kiểm
soát".

## Việc cần làm

1. **Cổng commit**
    - `.claude/settings.json`: matcher `"Bash|PowerShell"` cho `pre-commit-gate.sh`.
    - `pre-commit-gate.sh`: thay `case` bằng một regex khớp `git`, rồi không hay nhiều tùy
      chọn toàn cục (`-C <dir>`, `-c <k=v>`, `--git-dir=…`, `--work-tree=…`,
      `--no-pager`…), rồi `commit` là một từ riêng; khớp cả khi đứng sau `&&`, `;`, `|`.
      Đo trước những dạng tool PowerShell thật gửi (ví dụ `git commit -m @'…'@`), không
      đoán (`failure-modes.md` #4).
    - Script test (Git Bash và Linux): nạp JSON giả cho từng dạng — Bash và PowerShell;
      `git commit`, `git -C . commit`, `git -c user.name=x commit`,
      `cd x && git commit`, `git --no-pager commit` — với một invariant giả hỏng (biến môi
      trường trỏ `verify_invariants` sang một lệnh trả 1, hoặc cách tương đương không sửa
      tệp thật) → exit 2; ca âm `git commit-tree`, `git log --grep commit`,
      `echo "git commit"` → exit 0. Script cũng kiểm `settings.json` có matcher đúng.
2. **Tệp tắt cổng**: `.gitignore` thêm `.claude/no-commit-gate`, `.claude/no-stop-gate`,
   `.claude/.session-head.*`; comment đầu hai hook ghi "chỉ con người tạo tệp này".
   `permissions.deny` theo spec, nếu đo thấy chạy.
3. **Stop hook theo phiên**
    - `session-start.sh`: đọc stdin bằng `jq` (có fallback như `session-stop.sh`), lấy
      `session_id`; ghi `.claude/.session-head.<session_id>` (HEAD + ảnh chụp
      `git status --porcelain`) chỉ khi tệp chưa có. Xóa tệp mốc cũ quá 7 ngày.
    - `session-stop.sh`: đọc cùng `session_id`; chỉ tính đường dẫn mới hoặc đổi so với ảnh
      chụp; phần bẩn có sẵn được nêu riêng, không bắt commit. So commit với HEAD trong
      mốc. Không có mốc → hành xử như hôm nay nhưng nói rõ là không biết mốc.
    - Thêm ca vào script test: bẩn có sẵn + phiên không đổi gì → exit 0; phiên đổi một tệp
      → nhắc đúng tệp đó; SessionStart lần hai với `source=compact` không đổi mốc.
    - `session-start.sh:96`: bỏ con số ("the bug shapes this repository has produced"):
      `failure-modes.md` là chủ của số đếm.
4. **Plugin**: `CLAUDE.md` "Agent skills" thêm một câu: plugin cài theo từng checkout
   (`claude plugin install mattpocock-skills@claude-plugins-official --scope project`),
   kiểm bằng `claude plugin list`; chưa cài thì các lệnh `/ask-matt`, `/implement` không
   có. Cùng ý, ngắn hơn, ở `.claude/PLAN.md` lớp 5 và `docs/agents/issue-tracker.md`.
   Không đổi gì khác trong `CLAUDE.md`.
5. **`ui-quality.md`**: chép từ `C:/Users/phung/dw-elmichs/.claude/rules/ui-quality.md`;
   so với bản ở `C:/Users/phung/dw-proterial/.claude/rules/ui-quality.md` để lấy phần
   trung tính mà bản kia có hơn; gỡ tên sản phẩm, lời và ví dụ riêng của sản phẩm (thay
   bằng ví dụ trung tính hoặc bỏ); frontmatter `paths:` gồm `apps/web/**` và
   `packages/typescript/ui/**`. Không mâu thuẫn mục "Web UI" của `CLAUDE.md`; chỗ trùng
   thì trỏ về `CLAUDE.md`, không chép lần hai.
6. **Phạm vi rules**: đầu `code-quality.md` và `failure-modes.md` một câu: nạp mọi phiên có
   chủ ý vì áp cho mọi thay đổi (`CLAUDE.md` "Work style" mục 3). Không `paths:`.

## Tiêu chí chấp nhận

- Script test xanh; mỗi chốt trong bảng của spec có một lần gỡ làm nó đỏ, ghi lệnh và kết
  quả dưới `## Comments`.
- Một commit thật qua tool PowerShell trong phiên này bị cổng chặn khi invariant hỏng (thử
  trên nhánh nháp, rồi bỏ), ghi lại.
- `rg -i "elmich|proterial|bidding|e-hsdt|supply.chain" .claude/rules/ui-quality.md` không ra
  gì.
- `wc -l CLAUDE.md` không giảm ngoài câu thêm ở bước 4; `.claude/PLAN.md` dưới 80 dòng.
- `make ci` xanh.

## Nguồn

- Audit harness 6/10/2026, khu `dev-harness`: gap cổng vòng được (PowerShell, `git -C`),
  gap plugin, gap mốc Stop hook, gap Stop hook đếm cả cây, gap tệp tắt cổng, gap con số
  "seven", gap `ui-quality.md`, gap kích thước ngữ cảnh luôn nạp (real=true, kèm cảnh báo
  rằng hai rules không theo đường dẫn là có chủ ý).
- `.claude/settings.json`, `.claude/hooks/pre-commit-gate.sh:13-31`,
  `.claude/hooks/session-stop.sh:10-60`, `.claude/hooks/session-start.sh:75-100`,
  `.gitignore:60-67`, `~/.claude/plugins/installed_plugins.json`, `CLAUDE.md` "Agent
  skills", `.claude/PLAN.md` "How a feature is checked here".
- `failure-modes.md` #1, #3, #4, #5, #6.

## Comments
