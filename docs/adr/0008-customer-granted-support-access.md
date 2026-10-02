---
status: Proposed
date: 2026-09-30
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#104-bảo-mật-và-niềm-tin # hàng Truy cập hỗ trợ
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#24-khách-cần-chuẩn-bị-gì # onboarding bước 3, 4
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC13
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0007-bid-price-visible-to-pricing-and-owner-only.md
---

# Truy cập hỗ trợ do khách cấp: có hạn, theo phạm vi, không thấy giá, khách xem được nhật ký

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

Khi có khách thật, đội mình sẽ phải xem gói của khách: máy bóc sai một trang,
quy tắc báo sai sát giờ đóng thầu, hay khách mua dịch vụ nhập liệu lúc onboarding
(process 2.4, bước 3 và 4). Hôm nay chỉ có hai đường, và cả hai đều hỏng. Đường
thứ nhất là tự thêm mình làm `platform_admin`: vai này vượt mọi scope
(`packages/python/dw_platform/src/dw_platform/application/authorization.py:48-49`,
`if self.admin_role in context.roles: return True`), nên thấy cả giá, trái Q05 và
[ADR 0007 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0007-bid-price-visible-to-pricing-and-owner-only.md),
không có hạn, và khách không biết. Đường thứ hai là xin mật khẩu của khách, tức
dùng danh tính của người khác, trái nguyên tắc chỉ tin danh tính đã xác minh của
`CLAUDE.md`. Ngữ cảnh của Platform Operator thì cố ý không mang tenant
(`apps/api/src/dw_api/dependencies/auth.py:74-77`; ADR-002 mà code nhắc tới chưa
có trong repo), nên không đọc được dữ liệu nghiệp vụ.

Ngày 30/9/2026 Đạt chốt `[Đạt chốt]` hai ý: đội mình vào dữ liệu khách bằng một
quyền có thời hạn và không thấy giá; quyền đó thay cho `platform_admin` vượt mọi
scope. Các ý đó mang nhãn `[Đạt chốt]` ngay tại chỗ (quyết định 5, 9, 10). Phần
còn lại là đề xuất `[Đề xuất 30/9]`, và là quyết định của nền tảng vì mọi context
đều cần nó.

**Quyết định.**

1. **Khách nhờ, đội mình chọn người.** Người của khách bấm "Nhờ hỗ trợ" và chọn
   phạm vi (một gói hoặc cả workspace), chế độ (chỉ đọc, mặc định; hoặc nhập liệu
   kho năng lực), thời hạn và lý do. Đội mình chọn một nhân viên không xung đột
   lợi ích (D56, điểm mở 1). Khách không chọn người, nên lời từ chối vì xung đột
   không bao giờ tới tay khách.
2. **Người cấp chỉ trao được quyền mình đang có.** Khi tạo quyền, server kiểm scope
   xin cấp là tập con của scope chính người cấp đang giữ trong đúng workspace hoặc
   gói đó. Thực tế người cấp là `bid_owner`. `org_admin` không có scope đọc nghiệp
   vụ nào (`db/migrations/sql/0001_platform_reference.sql:76-81`), nên không tự cấp
   được; họ gửi được yêu cầu để `bid_owner` duyệt. Người cấp mất vai thì quyền mất
   hiệu lực.
3. **Nhân viên hỗ trợ dùng danh tính của chính họ, và ngữ cảnh không mang vai.**
   Người nhận phải là danh tính được nền tảng đánh dấu là nhân viên hỗ trợ, không
   phải một ô chọn phía client. MFA bắt buộc: server kiểm claim `amr`/`acr` khi
   dựng ngữ cảnh hỗ trợ. Ngữ cảnh lấy tenant và workspace từ quyền, `roles` rỗng,
   chỉ mang scope sinh từ quyền hỗ trợ, và không bao giờ hợp với vai của chính
   nhân viên, kể cả `platform_admin` (vai mà `authorization.py:48-49` cho qua mọi
   kiểm tra). Danh tính đó cũng không được thành member trong tenant khách:
   handler membership từ chối. Nếu không, `org_admin` (có `platform.members.write`)
   mời được nhân viên làm `bid_pricing`, thấy giá, không hạn.
4. **Scope là một danh sách đọc liệt kê cụ thể.** Context khai danh sách đó (với
   E-HSDT là dw_bid). Không bao giờ có scope xem giá, xuất giá, duyệt cổng, xác
   minh, đính chính hay miễn, dù khách chọn gì. Nhân viên hỗ trợ không duyệt, không
   xác minh, không đính chính, không miễn được gì vì ngữ cảnh không có các scope đó
   (SEC13), không phải nhờ GT01.
   Cho tới khi D29 và bản sửa TEN-04 xong, và mỗi đường đọc có test âm, danh sách
   cũng không có `approvals.read`, `runs.read`, `audit.events`, truy xuất tri thức
   hay chạy run. Thiếu scope chỉ chặn được route có kiểm scope: `GET /runs/{id}`
   hôm nay không kiểm scope nào và trả nguyên kết quả
   (`apps/api/src/dw_api/routes/v1/runs.py:41-58`), còn `GET /approvals` trả nguyên
   payload, chỉ lọc tenant (`apps/api/src/dw_api/routes/v1/approvals.py:44-76`).
5. **Không thấy giá** `[Đạt chốt]`. `[Đề xuất 30/9]` Hôm nay giá không nằm sau một
   scope, nên việc loại giá là một bộ lọc theo nhóm giá của phân loại dữ liệu, áp ở
   mọi đường đọc: tài liệu, ảnh trang, DTO phát hiện, payload duyệt, báo cáo, bản
   xuất. Mỗi đường một test âm. Cơ chế cụ thể theo D29. Trường `restricted` (số
   CCCD, lương; ADR nền tảng 0006) cũng bị che trong ngữ cảnh hỗ trợ: ở chế độ
   nhập liệu, nhân viên tải được tài liệu chứa chúng nhưng không xem được giá trị
   đã trích.
6. **Phạm vi có lớp thực thi.** Quyền theo gói chỉ chạm tài nguyên gắn `case_id`
   theo một danh sách cho phép viết ra, và không truy xuất tri thức. Quyền theo
   workspace ở tenant tư vấn (P2) chỉ mở sau khi có RLS theo workspace (D09,
   TEN-02), kèm test hai workspace. Hôm nay RLS chỉ cách ly tenant
   ([ADR 0006 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0006-consultancy-tenant-contractor-workspace.md),
   điểm mở 1).
7. **Chế độ nhập liệu kho chỉ thêm mới.** Nhân viên hỗ trợ chỉ tạo bằng chứng mới,
   ở trạng thái chưa xác minh cho tới khi người của khách xác minh (EV01). Không
   thay bản mới (EV03 `SUPERSEDED`), không rút, không xóa, không đính chính, không
   chạm dữ kiện cấp gói. Tác nhân ghi là `support:<grant_id>`, nhận ra cả người lẫn
   quyền, không phải `user:<id>`.
8. **Khách thấy và dừng được.** Mỗi lần xem, mỗi thao tác đều ghi audit; khách xem
   được nhật ký (ai, lúc nào, xem gì, sửa gì) và thu hồi quyền bất cứ lúc nào.
   Thu hồi có hiệu lực từ giao dịch kế tiếp (quyết định 9).
9. **Có hạn** `[Đạt chốt]`. `[Đề xuất 30/9]` Mặc định 72 giờ, tối đa 14 ngày mỗi
   quyền; gia hạn là một quyền mới, có lý do, có audit. Hết hạn và thu hồi được kiểm
   ở mỗi giao dịch, không cần ai nhớ thu hồi. Ngữ cảnh hỗ trợ không vào cache
   AccessContext 30 giây
   (`packages/python/dw_platform/src/dw_platform/adapters/persistence/caching_lookup.py:27`),
   vì lệnh xóa cache là fail-open
   (`packages/python/dw_platform/src/dw_platform/application/cache.py:7-9`). Run và
   bản xuất mở dưới quyền hỗ trợ kiểm lại quyền trước mỗi bước ghi hoặc trả kết quả.
10. **Quyền hỗ trợ thay cho `platform_admin` với dữ liệu của khách** `[Đạt chốt]`.
    `[Đề xuất 30/9]` Scope `platform.admin` (break-glass,
    `db/migrations/versions/b9862fa13a80_platform_separation_of_duty_rules_guard_.py:37`)
    chỉ dành cho sự cố của nền tảng, theo một quy trình riêng có người thứ hai
    duyệt.

## Phương án đã cân nhắc

- **Dùng `platform_admin`.** Loại: thấy giá, không hạn, khách không biết.
- **Khách chọn một nhân viên có tên** (bản đầu của ADR này). Loại: lời từ chối vì
  xung đột cho khách biết có một khách khác của mình cùng dự gói đó; thử lần lượt
  từng người thì dò ra được.
- **Xin mật khẩu hoặc mã OTP của khách.** Loại: dùng danh tính của người khác,
  audit ghi sai người.
- **Chỉ chia sẻ màn hình (Zalo, Meet).** Vẫn dùng được như cách nhẹ, nhưng không
  cho phép điều tra lúc khách không online, nên không thay được quyền hỗ trợ.

## Hệ quả

- Nền tảng có thêm một bảng quyền hỗ trợ có RLS, với phạm vi trung tính: tenant,
  workspace, `resource_type`, `resource_id` (không FK sang bảng của context), tập
  scope do context khai, người nhận, hạn, lý do, người cấp, lúc thu hồi. Nền tảng
  không biết "gói" hay "kho năng lực": thu hẹp theo gói và chế độ nhập liệu kho do
  dw_bid thực thi. Bộ dựng ngữ cảnh truy cập đọc bảng này. Việc này làm trên
  `main` trước (D06).
- Màn quản trị của khách có nút "Nhờ hỗ trợ", danh sách quyền đang có, nút thu hồi
  và nhật ký truy cập. Màn "quyền đang được cấp cho tôi" của nhân viên hỗ trợ dùng
  một hàm hẹp chỉ trả (tenant, workspace, phạm vi, hạn) cho user đã xác minh,
  không dùng role BYPASSRLS
  ([đề bài giao diện](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/ui-brief-2026-09-30.md)).
- Quy tắc SEC13 và các test âm của quyết định này nằm ở rule-spec: mỗi đường đọc
  dưới ngữ cảnh hỗ trợ (kể cả `GET /runs/{id}`, `GET /approvals`, truy xuất tri
  thức); cấp cho user không phải nhân viên hỗ trợ; người cấp trao quá quyền mình
  có; nhân viên giữ `platform_admin` dùng quyền hỗ trợ ở route giá; mời nhân viên
  làm member; xác minh hoặc đính chính bằng quyền hỗ trợ; hết hạn và thu hồi.

## Xung đột và điểm mở

1. **Xung đột lợi ích của nhân viên hỗ trợ** (D56). Máy cách ly tenant, nhưng người
   thì không: một nhân viên hỗ trợ hai khách cùng dự một số TBMT có thể làm lộ
   chiến lược của bên này sang bên kia. Đề xuất: kiểm bằng một hàm hẹp chỉ trả
   đúng/sai (kiểu `SECURITY DEFINER`), do dw_bid thỏa qua một port nền tảng khai,
   nên nền tảng không đọc bảng của dw_bid. Hàm tính cả workspace khác trong cùng
   tenant, và chạy lại khi có gói mới trong phạm vi một quyền đang mở. Đây là một
   ngoại lệ có chủ đích của Q07
   ([ADR 0004 của context](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/adr/0004-bid-rigging-check-within-one-tenant.md)),
   phải ghi vào ADR 0004 khi D56 được chốt. Còn cần quyết: ai trong đội mình được
   nhận quyền hỗ trợ.
2. **`platform_admin` hôm nay vẫn vượt mọi scope, kể cả giá** (D29). Ngữ cảnh hỗ
   trợ không mang vai nên không đi qua lỗ này, nhưng tính năng này không đóng lỗ đó
   cho người giữ vai. D29 vẫn phải quyết.
3. **Chế độ nhập liệu** mở cho nhân viên hỗ trợ ghi vào kho năng lực. Người cấp đã
   phải giữ quyền ghi đó (quyết định 2). Có cần thêm người thứ hai phía khách duyệt
   việc cấp chế độ này không: gộp vào D56.
4. **Hình thái P4, P5.** ADR này áp cho P1–P3. Ở P4, P5 data plane nằm ở hạ tầng
   khách, P5 không có kết nối ra, và nhân viên của mình không có danh tính trong
   Keycloak hay PostgreSQL của khách. Danh tính nhân viên hỗ trợ tới data plane thế
   nào (tài khoản cục bộ do khách tạo, hay liên kết IdP) đi cùng câu chủ membership
   ở [ADR nền tảng 0005](0005-control-plane-data-plane-boundary.md) điểm mở 2, và
   D41.
5. **Điều kiện mở cho khách pilot.** Quyền hỗ trợ chưa mở cho khách pilot chừng nào
   D29 (đường đọc giá), D30 (lộ chéo workspace), bản sửa TEN-04 (route không kiểm
   scope, đọc chéo workspace) và, với P2, D09 chưa xong.

Các mã như `TEN-02`, `TEN-04` là mục trong [bản đối chiếu tài liệu với repo ngày 29/9/2026](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/audit-2026-09-29.md).
