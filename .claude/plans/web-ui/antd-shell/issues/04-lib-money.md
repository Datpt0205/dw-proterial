# 04 — `lib/money.ts`

Status: ready-for-agent
Blocked by: 02
Area: web-ui

## Mục tiêu

Một chỗ duy nhất định dạng và đọc số tiền: `18.450.000.000 đ`, không bao giờ "₫"; đọc
được số dán vào theo cả hai kiểu ngăn nghìn; từ chối số lẻ mơ hồ thay vì nhân 1 000.
Đọc số thành chữ không ở đây: thuộc `dw_bid` (D12).

## Việc cần làm

- Tạo `apps/web/lib/money.ts`:
    - `formatMoney(amount: number)` → `18.450.000.000 đ`. Ngăn nghìn bằng dấu chấm; giữa
      số và "đ" là khoảng trắng không ngắt (U+00A0) để "đ" không rơi xuống dòng; số âm có
      dấu trừ.
    - `formatMoneyNumber(amount)` → `18.450.000.000` (cho ô nhập có hậu tố "đ" riêng).
    - `formatMoneyShort(amount)` → `18,45 tỷ`: chia 1 tỷ, tối đa 2 chữ số lẻ, dấu phẩy
      thập phân. Chú thích ghi rõ: không dùng cho giá trị đang đem so ngưỡng hay đang
      đính chính, vì `14.995.000.000` và `15.000.000.000` cùng ra `15 tỷ`.
    - `formatCount(n)` → `1.234` (số đếm, cùng cách ngăn nghìn).
    - `parseMoney(text)` trả một trong ba dạng: `{ kind: "empty" }`,
      `{ kind: "ok", value: number }`, `{ kind: "invalid", reason: string }`.
    - Nhận `18.450.000.000`, `18,450,000,000`, `18450000000 đ`, `18.450.000.000đ`, và
      `18 450 000 000` có khoảng trắng hai đầu.
    - Từ chối, kèm lý do tiếng Việt không trách người dùng ("Số tiền phải là số
      nguyên"): `1.5`, `1,5`, `12.345,67`, chữ lẫn số, số vượt
      `Number.MAX_SAFE_INTEGER` ("Số tiền vượt giới hạn").
    - `moneyInputFormatter` và `moneyInputParser` cho antd `InputNumber`
      (`precision={0}`, căn phải, hậu tố "đ"), dùng hai hàm trên.
- Luật ESLint trong `apps/web/.eslintrc.json`: ngoài `lib/money.ts` cấm
  `Intl.NumberFormat` và thuộc tính `currency: "VND"`. Lệnh cấm `toLocaleString` của
  ticket 03 đã chặn đường còn lại; nếu 03 chưa xong thì ticket này thêm luật đó, trừ
  `lib/money.ts` và `lib/dates.ts`.
- Thêm một mục tiền vào fixture `/dev-login/ui-kit` khi ticket 05 đã có nó; nếu 04
  xong trước 05 thì 05 thêm.

## Tiêu chí chấp nhận

Test vitest ở `apps/web/lib/__tests__/money.test.ts`:

- [ ] `formatMoney(1285000)` = `1.285.000 đ`; `formatMoney(18450000000)` =
      `18.450.000.000 đ`; `formatMoney(0)` = `0 đ`. Không chuỗi nào chứa "₫".
      Thay bằng `Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" })` thì
      test đỏ.
- [ ] `formatMoneyShort(18450000000)` = `18,45 tỷ`; một test ghi rõ
      `formatMoneyShort(14995000000) === formatMoneyShort(15000000000)`, là lý do hàm này
      bị hạn chế.
- [ ] `parseMoney` ra `ok 18450000000` cho năm dạng nhận ở trên; ra `invalid` cho
      `1.5`, `1,5`, `12.345,67`, `12a`, `9007199254740993`; ra `empty` cho `""` và `"  "`.
      Bỏ nhánh từ chối `1.5` thì test đỏ (hàm sẽ đọc thành 15).
- [ ] Render antd `InputNumber` với `moneyInputFormatter`/`moneyInputParser` trong
      jsdom: gõ `18450000000` thì ô hiện `18.450.000.000`, giá trị là số
      `18450000000`; dán `18,450,000,000` ra cùng giá trị.
- [ ] Playwright trên fixture (sau 05): gõ thêm chữ số vào giữa số đã có thì con trỏ
      không nhảy về cuối. Đo hành vi của antd trước; nếu antd làm nhảy con trỏ, ghi lại
      dưới Comments và chọn cách sửa trước khi đóng ticket.
- [ ] Một test chạy ESLint trên đoạn có `currency: "VND"` đặt ở một trang ra lỗi; đặt ở
      `lib/money.ts` thì không.
- [ ] `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Tiền" (chép từ design v3 `v3-kit.js` `money`, `moneyNum`, `short`,
  `parseMoney`; `V3Field.dc.html` kiểu `money`).
- `ui-quality.md` §8, §9 (nhánh `bidding`): một formatter tiền, "đ" thay "₫", dán theo
  cả hai kiểu, số nguyên, số lẻ dấu chấm thì đọc đúng hoặc từ chối.
- D12 (Đạt 2/10/2026): hàm xử lý tiếng Việt nằm trong `dw_bid`, nên đọc số thành chữ
  không ở `lib/money.ts`.
- `failure-modes.md` #2 (một dữ kiện, hai bản sao), #4 (đo `InputNumber` trước khi dựa
  vào nó).

## Comments
