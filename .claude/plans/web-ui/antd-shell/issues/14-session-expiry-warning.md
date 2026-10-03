# 14 — Cảnh báo phiên sắp hết hạn

Status: ready-for-agent
Blocked by: 03, 06
Area: web-ui

## Mục tiêu

Người đang gõ dở không mất phiên và dữ liệu mà không được báo trước (WCAG 2.2.1). Hai
phút trước khi phiên đăng nhập hết, một hộp thoại cho họ ở lại bằng một lần bấm.

Hôm nay `apps/web/lib/auth/auth-context.tsx` đặt `kc.onTokenExpired`: làm mới token,
và khi phiên SSO đã hết thì `kc.login(...)` chuyển trang ngay, không báo gì.

Realm local (`infra/keycloak/dw-realm.json`) đặt cả ba giá trị bằng 28800 giây (8 giờ):
`accessTokenLifespan`, `ssoSessionIdleTimeout` và `ssoSessionMaxLifespan`. Mỗi lệnh gọi
API chạy `kc.updateToken(30)` (`currentAccessToken` trong `lib/session.ts`), tức chỉ
làm mới trong 30 giây cuối của token 8 giờ, mà lúc đó phiên SSO cũng vừa chạm thời hạn
tối đa 8 giờ. Chuông thông báo gọi API mỗi 60 giây (`components/notification-bell.tsx`,
`POLL_MS`), nên một tab đang mở không bao giờ rảnh. Vậy trên realm local, mọi người bị
đăng xuất 8 giờ sau khi đăng nhập, dù đang dùng hay không, và không có cách gia hạn tại
chỗ. Token dev cũng sống 8 giờ và không làm mới (`apps/api/src/dw_api/routes/v1/dev.py`).

Đường chính của ticket này vì thế là chạm thời hạn tối đa: hộp báo trước 2 phút, "Ở lại
đăng nhập" không gia hạn được, hộp đổi sang "Đăng nhập lại" mà không bỏ chữ đang gõ.
Gia hạn tại chỗ là đường phụ, cho realm nào đặt thời hạn tối đa dài hơn token.

## Việc cần làm

- Đo trước (`failure-modes.md` #4), ghi dưới Comments:
    - ở chế độ `oidc`, `kc.refreshTokenParsed.exp` có đúng là lúc phiên SSO hết (rảnh
      quá lâu hoặc chạm thời hạn tối đa) không; thử trên realm local với
      `ssoSessionMaxLifespan` và `accessTokenLifespan` hạ còn vài phút, rồi riêng
      `ssoSessionIdleTimeout`;
    - realm dev dùng chung có đặt ba giá trị khác realm local không;
    - lệnh gọi mỗi 60 giây của chuông có giữ cho phiên không bao giờ hết vì rảnh không
      (nếu có, ca "rảnh quá lâu" không xảy ra khi tab còn mở);
    - `kc.updateToken(-1)` có kéo dài phiên rảnh không, và trả gì khi đã chạm thời hạn
      tối đa;
    - ở chế độ `dev`, `exp` trong token dev đọc được ở trình duyệt.
- `apps/web/components/session-expiry-warning.tsx`, gắn một lần trong
  `components/app-frame.tsx` khi đã đăng nhập:
    - giờ hết phiên đến từ `AuthProvider` (một chỗ đọc token), không component nào tự
      giải mã token;
    - hẹn giờ theo thời điểm tuyệt đối, tính lại khi `visibilitychange` (tab nền bị
      trình duyệt làm chậm hẹn giờ) và sau mỗi lần làm mới token;
    - còn 2 phút thì mở hộp thoại qua `App.useApp().modal` (06): tiêu đề "Phiên đăng
      nhập sắp hết hạn" (đề xuất), câu "Phiên sẽ hết lúc {giờ}." với giờ in bằng
      `formatInstant` (03), nút chính "Ở lại đăng nhập" nhận focus, nút "Đăng xuất";
    - "Ở lại đăng nhập" làm mới phiên tại chỗ khi realm cho gia hạn; trang, ô đang gõ
      và URL giữ nguyên;
    - làm mới không được (đã chạm thời hạn tối đa): hộp đổi sang câu "Phiên đã hết. Đăng
      nhập lại để tiếp tục." (đề xuất) và nút "Đăng nhập lại"; không tự chuyển trang
      trước khi người dùng bấm.
- `AuthProvider` phơi thời điểm hết phiên và một hàm gia hạn; ở chế độ `dev` gia hạn là
  không làm được (token dev không làm mới), hộp đi thẳng sang "Đăng nhập lại".
- Không đổi luồng chuyển trang khi API trả 401 trong ticket này; ghi dưới Comments nếu
  đo thấy nó làm mất dữ liệu đang gõ.

## Tiêu chí chấp nhận

- [ ] Vitest với đồng hồ giả: phiên hết sau 10 phút; ở 7:59 chưa có hộp thoại, ở 8:00
      có, focus ở "Ở lại đăng nhập". Gỡ hẹn giờ thì test đỏ.
- [ ] Vitest: bấm "Ở lại đăng nhập" gọi hàm gia hạn một lần, hộp đóng, hẹn giờ đặt lại
      theo giờ hết mới; hàm gia hạn thất bại thì hộp hiện "Đăng nhập lại" và chưa gọi
      `login`.
- [ ] Vitest: tab bị ẩn qua mốc 2 phút rồi hiện lại (`visibilitychange`) thì hộp hiện
      ngay.
- [ ] Vitest: một ô nhập có chữ trước khi hộp mở vẫn giữ nguyên chữ sau khi bấm "Ở lại
      đăng nhập".
- [ ] Phép thử tay trên realm local với `ssoSessionMaxLifespan` và
      `accessTokenLifespan` hạ còn 3 phút: hộp hiện lúc còn 2 phút; bấm "Ở lại đăng
      nhập" thì hộp đổi sang "Đăng nhập lại", trang không tải lại và chữ trong ô đang gõ
      còn nguyên đến khi người dùng bấm. Ghi kết quả dưới Comments.
- [ ] `pnpm --filter @dw/web test`, `pnpm run lint`, `pnpm run typecheck` xanh.

## Nguồn

- Spec, mục "Khung" (cảnh báo phiên).
- `ui-quality.md` §4 ("Session expiry warns a few minutes ahead with a way to stay
  signed in (WCAG 2.2.1) and never discards input") (nhánh `bidding`).
- `apps/web/lib/auth/auth-context.tsx` (`onTokenExpired`), `apps/web/lib/session.ts`
  (`currentAccessToken`), `infra/keycloak/dw-realm.json`.
- Spec, Ngoài phạm vi trước 3/10/2026 ghi mục này là P1; chuyển vào phạm vi vì là yêu
  cầu truy cập.
- `failure-modes.md` #4.

## Comments
