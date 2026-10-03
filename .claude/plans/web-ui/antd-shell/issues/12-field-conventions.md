# 12 — Quy ước trường: nhãn, gợi ý, lỗi, bộ đếm, ô giờ

Status: ready-for-agent
Blocked by: 03, 04, 05, 07
Area: web-ui

## Mục tiêu

Mọi trường trong `Form` của antd trông và nói như design, từ theme và một vài hàm dùng
chung, không bọc lại `Input` hay `Form.Item`. Hôm nay chỉ ô tiền có ticket (04); nhãn,
dấu bắt buộc, gợi ý, lỗi, bộ đếm ký tự và hậu tố "giờ Việt Nam" chưa ticket nào nhận.

## Việc cần làm

- `packages/typescript/ui/src/theme.ts`, component token của `Form` (đúng spec mục
  "Nút (V3Btn) và trường (V3Field)"):
    - nhãn 13px (`labelFontSize`), đậm 500, nằm trên ô; antd 6.6.5 không có token cho độ
      đậm của nhãn, nên đo trước rồi đặt một quy tắc trong `@dw/ui`, không ở trang;
    - dấu `*` màu lỗi (`labelRequiredMarkColor` bằng `colorError`); `requiredMark` đặt
      một lần trên `ConfigProvider`;
    - gợi ý (`extra`) và lỗi 12px dưới ô; lỗi có biểu tượng trước chữ. Đo cách antd vẽ
      dòng lỗi trước khi chọn chỗ đặt biểu tượng (`failure-modes.md` #4).
- `packages/typescript/ui/src/field-count.ts`, xuất từ `index.ts`: một hàm
  `fieldCount(max)` trả cấu hình `count` của antd `Input`/`Input.TextArea`
  (`{ max, show }`):
    - dưới 90% của `max`: không hiện gì;
    - từ 90% tới `max`: "Còn N ký tự";
    - vượt `max`: "Vượt N ký tự", màu lỗi, và ô ở trạng thái lỗi. Không cắt chữ người
      dùng đã gõ (không dùng `exceedFormatter` để cắt).
- Ô giờ: `DatePicker showTime` đọc và ghi qua `pickerValueToInstant` và
  `instantToPickerValue` của `lib/dates.ts` (03), hậu tố là `TIME_ZONE_LABEL`
  ("giờ Việt Nam"), định dạng `HH:mm DD/MM/YYYY`. Ô ngày `DD/MM/YYYY`. Chữ hậu tố đọc từ
  hằng của 03, không viết lại.
- Ô tiền dùng `moneyInputFormatter`/`moneyInputParser` của 04; ticket này chỉ đặt nó cạnh
  các trường khác trên fixture.
- Thêm mục "Trường" vào fixture `/dev-login/ui-kit`: một `Form` dọc có trường bắt buộc,
  gợi ý, lỗi, ô chữ có bộ đếm (gần hết và vượt), ô giờ, ô ngày, ô tiền.

## Tiêu chí chấp nhận

- [ ] Vitest `fieldCount(100)`: 89 ký tự không hiện gì; 90 hiện "Còn 10 ký tự"; 100 hiện
      "Còn 0 ký tự"; 103 hiện "Vượt 3 ký tự". Đổi ngưỡng thành 80% thì test đỏ.
- [ ] Vitest: một `Input` dùng `fieldCount(10)` với 12 ký tự vẫn giữ đủ 12 ký tự trong
      ô.
- [ ] Playwright `@ui` trên fixture: nhãn có `font-size` 13px và `font-weight` 500;
      trường bắt buộc có dấu `*` màu `colorError`; dòng lỗi 12px có biểu tượng; ở chế độ
      tối các chữ này đạt 4,5:1 trên nền.
- [ ] Playwright `@tz` trên fixture: chọn 09:00 14/10/2026 ở ô giờ thì giá trị ghi ra là
      `2026-10-14T02:00:00Z`, cả ở `tz-los-angeles`; ô có hậu tố "giờ Việt Nam".
- [ ] Không có chuỗi "giờ Việt Nam" nào ngoài `lib/dates.ts` (grep trong `apps/web` và
      `packages/typescript/ui`, bỏ test).
- [ ] Ở `phone-320` mục "Trường" không cuộn ngang.
- [ ] `pnpm --filter @dw/ui test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Nút (V3Btn) và trường (V3Field)" (chép từ design v3 `V3Field.dc.html`).
- `CLAUDE.md` "Web UI": `@dw/ui` không bọc lại antd; một formatter giờ.
- `ui-quality.md` §8 (ô chọn giờ đọc theo giờ Việt Nam), §9 (nhãn hiện, `requiredMark`
  một lần trên `ConfigProvider`, antd tự nối lỗi bằng `aria-describedby`) (nhánh
  `bidding`).
- Ticket 03 (`TIME_ZONE_LABEL`, hàm ô chọn giờ), 04 (ô tiền).
- `failure-modes.md` #2 (chữ "giờ Việt Nam" một chủ), #4.

## Comments
