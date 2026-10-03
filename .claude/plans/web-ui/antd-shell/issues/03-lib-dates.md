# 03 — `lib/dates.ts` theo giờ Việt Nam

Status: ready-for-agent
Blocked by: 02
Area: web-ui

## Mục tiêu

Một formatter duy nhất cho mọi thời điểm trên web: tính theo `Asia/Ho_Chi_Minh`, giờ
trước ngày, có nhãn "giờ Việt Nam", không theo múi giờ của máy người xem. Hạn chỉ có
ngày là một ngày lịch, không phải nửa đêm. "Chưa rõ" và "không có" là hai thứ khác
nhau mà kiểu dữ liệu bắt người gọi phải chọn.

Hôm nay `apps/web/lib/dates.ts` dùng `new Date(iso)` với giờ của máy, in ngày trước
giờ, và trả "—" cho `null`, nên một hạn máy không đọc được trông như "không có hạn".

## Việc cần làm

- Viết lại `apps/web/lib/dates.ts` trên dayjs (cài ở 02) với plugin `utc` và
  `timezone`. Một hằng `VN_TIME_ZONE = "Asia/Ho_Chi_Minh"` và một hằng
  `TIME_ZONE_LABEL = "giờ Việt Nam"`, chỉ ở tệp này.
- Hàm, đúng các dạng ở spec mục "Giờ":
    - `formatInstant(iso)` → `09:00 14/10/2026 (giờ Việt Nam)`.
    - `formatInstantCell(iso)` → `09:00 14/10/2026` (tiêu đề cột dùng
      `TIME_ZONE_LABEL`).
    - `formatInstantDate(iso)` → ngày lịch Việt Nam của một thời điểm, `14/10/2026`.
    - `formatCalendarDate(date)` nhận `YYYY-MM-DD`, trả `14/10/2026`; không đi qua
      `new Date`.
    - `formatDateUnknownTime(date)` → `14/10/2026 · chưa rõ giờ`.
    - `formatEndOfDay(date)` → `hết ngày 25/02/2027 (giờ Việt Nam)`.
    - `formatRelative(iso, now)` → `3 phút trước · 14:07 30/09/2026 (giờ Việt Nam)`;
      "vừa xong" dưới 1 phút; "N phút trước" dưới 60 phút; "N giờ trước" cùng ngày Việt
      Nam; "Hôm qua" theo lịch Việt Nam; xa hơn thì ngày. `now` do người gọi truyền vào,
      không đọc đồng hồ trong hàm.
    - `pickerValueToInstant(value: Dayjs)` và `instantToPickerValue(iso)`: đọc giá trị của
      `DatePicker showTime` theo giờ treo tường Việt Nam, không qua
      `value.toISOString()`.
- Không hàm nào nhận `null` hay `undefined`. Chuỗi thời điểm không có `Z` hay offset
  (`2026-10-14T09:00:00`) thì ném lỗi; `formatCalendarDate` nhận chuỗi có giờ thì ném
  lỗi.
- Sửa 6 chỗ gọi: `app/admin/feedback/page.tsx`, `app/approvals/page.tsx`,
  `app/audit/page.tsx`, `app/knowledge/page.tsx` (2 chỗ),
  `app/admin/separation-of-duties/page.tsx` và `components/notification-bell.tsx`
  (đang dùng `toLocaleString()`). Chỗ nào giá trị có thể `null` thì rẽ nhánh rõ ở chỗ
  gọi, có chú thích nó nghĩa là "không có" hay "chưa rõ".
- Luật ESLint trong `apps/web/.eslintrc.json`, trừ `lib/dates.ts` và `lib/money.ts`:
  cấm gọi `toLocaleString`, `toLocaleDateString`, `toLocaleTimeString`; cấm
  `Intl.DateTimeFormat`; cấm `import dayjs` (cho phép `import type { Dayjs }`).
- Script `test:tz` trong `apps/web/package.json` chạy lại test của `lib/dates.ts` với
  `TZ=America/Los_Angeles`.

## Tiêu chí chấp nhận

Test vitest ở `apps/web/lib/__tests__/dates.test.ts`, chạy bằng
`pnpm --filter @dw/web test` và `pnpm --filter @dw/web test:tz`, cùng kết quả:

- [ ] `formatInstant("2026-10-14T02:00:00Z")` = `09:00 14/10/2026 (giờ Việt Nam)`.
- [ ] Biên ngày: `2026-10-13T17:00:00Z` → `00:00 14/10/2026`; `2026-10-13T23:59:00Z` →
      `06:59 14/10/2026` (ngày UTC còn là 13); `2026-10-14T16:59:00Z` → `23:59 14/10/2026`.
- [ ] `formatInstantDate("2026-10-13T18:30:00Z")` = `14/10/2026`.
- [ ] `formatCalendarDate("2026-10-14")` = `14/10/2026` dưới `TZ=America/Los_Angeles`.
      Thay bằng `new Date(date)` thì ca này ra `13/10/2026` và đỏ.
- [ ] `formatEndOfDay("2027-02-25")` = `hết ngày 25/02/2027 (giờ Việt Nam)`.
- [ ] `formatRelative` với `now = 2026-09-30T07:10:00Z` (14:10 giờ Việt Nam):
    - `2026-09-30T07:07:00Z` → `3 phút trước · 14:07 30/09/2026 (giờ Việt Nam)`;
    - `2026-09-29T17:30:00Z` (00:30 ngày 30 giờ Việt Nam, ngày 29 giờ UTC) → bắt đầu
      bằng `14 giờ trước`, không phải "Hôm qua";
    - `2026-09-29T16:30:00Z` → `Hôm qua · 23:30 29/09/2026 (giờ Việt Nam)`;
    - 30 giây trước → bắt đầu bằng `vừa xong`.
- [ ] `pickerValueToInstant` của giá trị chọn 09:00 14/10/2026 ra thời điểm
      `2026-10-14T02:00:00Z`, cả khi `TZ=America/Los_Angeles`.
- [ ] `formatInstant("2026-10-14T09:00:00")` ném lỗi; gỡ kiểm tra đó thì test đỏ.
- [ ] Không chuỗi nào in ra có ngày trước giờ, và không có "—".
- [ ] Một test chạy ESLint (`ESLint#lintText`) trên đoạn có `new Date().toLocaleString()`
      và đoạn có `import dayjs from "dayjs"` đặt ở một trang: ra lỗi đúng luật; cùng đoạn
      đặt ở `lib/dates.ts` thì không. Nếu cấu hình `.eslintrc` cũ làm API khó dùng, ghi
      phép thử tay (thêm dòng vi phạm, `pnpm --filter @dw/web lint` đỏ) vào Comments.
- [ ] `pnpm run lint`, `pnpm run typecheck` xanh sau khi sửa 6 chỗ gọi.

## Nguồn

- Spec, mục "Giờ" (chép từ design v3 `v3-kit.js` hàm `T`).
- `CLAUDE.md` "Web UI" (dayjs `vi` sau `lib/dates.ts`, một formatter).
- `ui-quality.md` §8 (nhánh `bidding`): giờ trước ngày, hạn chỉ có ngày, ô chọn giờ,
  "unknown is not none".
- ADR ctx 0021 (nhánh `bidding`, Proposed): lưu tuyệt đối, hiện và rút ngày theo giờ
  Việt Nam; "hết ngày" là nửa mở; các ca biên 00:00, 06:59, 23:59.
- `failure-modes.md` #3, #4 (đo plugin `timezone` của dayjs trên Node 22 và trình
  duyệt trước khi dựa vào nó).
- Spec, Câu hỏi còn mở 2 (`platform.tenants.timezone` không ai đọc).

## Comments
