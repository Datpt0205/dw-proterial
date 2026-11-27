# Phần dùng chung DW1–DW2: có gì, thiếu gì, ai làm

Dành cho đội DW1, đội DW2 và đội hỗ trợ (FSO). "Phần chung" là thứ nằm ở nền
tảng hoặc package dùng chung. **DW2 không viết lại bản của mình**: mỗi sự thật
một chủ (`CLAUDE.md`). Cần khác đi thì sửa ở chỗ chung, hoặc khai một Protocol
ở phía DW2 và để composition root nối.

Đọc từ code ngày 2026-11-26. Mỗi việc thiếu là một mảnh **làm được độc lập**,
ghi cỡ việc (**S** ≤ 1 ngày, **M** 2–4 ngày, **L** ≥ 1 tuần) và có chặn UAT DW1
không. Cột "Ai" là đề xuất, chốt trong buổi họp. DW1 = `dw_sales` +
`apps/web/app/sales`; DW2 = `dw_purchasing` + `apps/web/app/purchasing`.

**Đối chiếu lại với code ngày 2026-11-27** (sau ticket DW1 70–85). Cột "Tình
trạng" ghi: **Xong** (commit), **ticket NN** (`.claude/plans/shared/issues/`,
danh sách và thứ tự làm ở `.claude/plans/shared.md`), hoặc **Sales NN**
(ticket DW1 đã có, `.claude/plans/sales/dw1-production/issues/`, không mở
ticket thứ hai). "Chờ …" là việc không làm được ở đây, ghi rõ chờ ai.

---

## 0. Tóm tắt

**DW1 có, DW2 chưa có, nên nâng lên nền tảng trước khi DW2 làm** (để không
chép code): giao việc (assignee), push iPhone, SLA và nhắc việc, chat gắn hồ
sơ cùng thao tác trong chat, client gọi Bravo gateway và vé duyệt, liên kết
định danh, shadow mode, hàng "Việc của tôi".

**Việc chặn UAT DW1** (đánh dấu ⚑ bên dưới): flow gửi thư, watchdog máy sync,
push iPhone thật, gateway (lưu SO có sẵn, quyền lệnh, `CreateProcess`, 2 login
của IT), AD, model nhà máy, máy chủ nhà máy. Ngày 27/11: lưu SO có sẵn,
`CreateProcess` và code quyền lệnh đã xong; code còn làm được ở đây là
watchdog (ticket 01) và để watch Bravo theo đúng Bravo đang dùng (ticket 02,
không thì gateway chỉ có UAT tự dừng); còn lại chờ IT, buổi UAT, máy nhà máy.

---

## 1. Khung chat

**Đã có**

- `@dw/ui` `AssistantChat` (`packages/typescript/ui/src/assistant-chat.tsx`,
  Ant Design X): bong bóng hỏi/đáp, nhãn "Máy viết", nút chép, các bước DW làm
  (`ThoughtChain`), "Căn cứ" trỏ tới bản ghi, câu gợi ý khi chat trống, nút dừng,
  báo mất mạng.
- Trả lời chạy chữ dần (SSE `step`/`delta`/`replace`, `apps/web/lib/chat-live.ts`).
- DW1: 10 loại câu hỏi; chat gắn hồ sơ (`case-chat.tsx`); widget "Hỏi DW1"
  (`assistant-widget.tsx`).
- **Thao tác trong chat chỉ có 2 thứ**: một ô `action` cắm nút có sẵn của trang
  (soạn trả lời, nhắc khách, tóm tắt luồng thư), và một nút "Xác nhận" cho đề
  xuất (quyết cờ, hoặc mở phê duyệt ghi Bravo; việc duyệt vẫn làm ở chỗ khác).
- DW2: trang `purchasing/assistant` dùng cùng khung; 3 loại câu hỏi; **không có
  chat gắn hồ sơ, không có thao tác, không có widget**.

**Còn thiếu**

| Việc                                                                                                                  | Cỡ  | UAT | Ai        | Tình trạng 27/11                                                                                                                           |
| --------------------------------------------------------------------------------------------------------------------- | --- | --- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Tin nhắn có kiểu (`card`, `decision`, `form`, `choice`, `file`, `table`) do server gửi, thay cho một ô `action` tự do | M   |     | FSO       | ticket 17 (`decision` ở 18, `form` ở 19, `file` ở 23)                                                                                      |
| Duyệt / trả lại ngay trong chat (thẻ quyết định gọi API duyệt, gắn phiên bản đối tượng)                               | M   |     | FSO       | ticket 18 (cũng là phần còn lại của Sales 79)                                                                                              |
| **Giao người trong chat** ("giao cho Khoa"): thẻ chọn người lấy danh sách người có quyền, như nút "Giao lại"          | M   |     | FSO       | **Xong** cho DW1 (`0135304b`): code tìm đúng một người trong danh sách được giao, nút "Giao cho …"; trùng tên thì hiện thẻ chọn: ticket 17 |
| @nhắc tên một người trong ô gõ, người đó nhận thông báo kèm link tới câu chat                                         | M   |     | FSO       | ticket 22                                                                                                                                  |
| Đính kèm file trong chat (qua quét virus và sandbox đọc file)                                                         | L   |     | FSO       | ticket 23 (tải, quét, đọc) → 24 (câu trả lời đọc file)                                                                                     |
| Câu gợi ý tiếp theo sau mỗi câu trả lời (hiện chỉ có khi chat trống)                                                  | S   |     | FSO       | ticket 20                                                                                                                                  |
| Form nhỏ trong chat (sửa ngày, số lượng) thay cho gõ tự do                                                            | M   |     | FSO       | ticket 19                                                                                                                                  |
| Nút thích/không thích câu trả lời, lưu lại làm ví dụ                                                                  | S   |     | FSO       | ticket 21                                                                                                                                  |
| Báo khi câu trả lời xong lúc widget đang đóng (hiện chỉ có dấu chưa đọc)                                              | S   |     | FSO       | ticket 20                                                                                                                                  |
| Đưa vỏ widget và bố cục chat hồ sơ lên `@dw/ui`                                                                       | M   |     | Đạt duyệt | ticket 27 (nâng khi DW2 dùng; Đạt duyệt props)                                                                                             |
| Một kho hội thoại chung cho mọi DW (DW1 theo hồ sơ + 1 chung; DW2 theo phiên có tên) và giao thức đề xuất/xác nhận    | L   |     | Đạt + FSO | ticket 35, chờ Đạt quyết (ADR)                                                                                                             |
| DW2: chat gắn hồ sơ PR, thao tác "gửi RFQ", "duyệt"                                                                   | M   |     | DW2       | ticket 27 (chat theo PR) → 28 (thao tác)                                                                                                   |
| Đo chạy chữ qua Cato (TLS inspection có thể giữ cả câu) trên máy thật                                                 | S   | ⚑   | Đạt       | Sales 83, chờ Đạt trên máy nhà máy                                                                                                         |

## 2. Phê duyệt (người trong vòng)

**Đã có:** `ApproveAndResumeService` (quyết, chờ, rút lại, guard, vé ký cho
Bravo); trang `/approvals`; duyệt qua Zalo bằng mã 6 số; DW1 duyệt ngay trong
Việc cần làm và trang hồ sơ; DW2 duyệt trong Việc của tôi (bắt buộc lý do, gắn
phiên bản); tách nhiệm (maker ≠ checker). Duyệt hàng loạt **cố ý không có**.

**Còn thiếu**

| Việc                                                                                  | Cỡ  | UAT | Ai  | Tình trạng 27/11                                                                 |
| ------------------------------------------------------------------------------------- | --- | --- | --- | -------------------------------------------------------------------------------- |
| Ủy quyền khi vắng: A giao quyền duyệt cho B trong khoảng ngày, có audit               | L   |     | FSO | ticket 34, chờ Đạt quyết ủy quyền là gì (khuyến nghị: admin cấp vai có hạn ngày) |
| Chuyển một phê duyệt đang chờ sang người khác cùng quyền                              | M   |     | FSO | ticket 12                                                                        |
| SLA và nhắc/escalate cho phê duyệt ở nền tảng (hiện chỉ DW1 có, trong `followups.py`) | M   |     | FSO | ticket 11                                                                        |
| Một "Việc của tôi" chung cho mọi DW (hiện DW1, DW2 mỗi bên một trang)                 | M   |     | FSO | ticket 15                                                                        |
| Duyệt trên điện thoại (`/approvals` hiện là bảng cho máy tính)                        | S–M |     | FSO | ticket 13 (thẻ chờ duyệt đã là `Card`; còn bảng "đã quyết" và đo ở 390/320 px)   |
| Duyệt phiên bản quy tắc, layout, dữ liệu gốc ngay trong hàng việc DW1 (hiện chỉ link) | M   |     | DW1 | ticket 14 (layout vẫn link vì cần phiên bản layout)                              |
| Hiện "đã báo ai, lúc nào" khi escalate                                                | S   |     | FSO | ticket 11                                                                        |

## 3. Giao việc

**Đã có (chỉ DW1):** người phụ trách hồ sơ lấy theo Sales PIC của khách;
trưởng phòng giao lại (kiểm phiên bản, audit, thông báo); danh sách người được
giao lấy đúng từ hàm quyết quyền (`ScopeHoldersPort`); nút `reassign.tsx`.

**Còn thiếu**

| Việc                                                                          | Cỡ  | UAT | Ai  | Tình trạng 27/11                          |
| ----------------------------------------------------------------------------- | --- | --- | --- | ----------------------------------------- |
| Nâng phần giao việc lên nền tảng (port, danh sách ứng viên, audit, thông báo) | M   |     | FSO | ticket 08                                 |
| DW2: thêm người phụ trách hồ sơ (buyer), luật giao, API và nút giao lại       | M–L |     | DW2 | ticket 29; luật tự giao chờ Proterial/Đạt |
| PIC tự "nhận việc" hồ sơ chưa ai nhận                                         | S   |     | FSO | ticket 08                                 |
| Giao lại hàng loạt (người vắng, chuyển hết hồ sơ)                             | M   |     | FSO | ticket 09                                 |
| Khối lượng việc từng người trên màn của trưởng phòng                          | M   |     | FSO | ticket 10                                 |
| Giao người từ chat (mục 1)                                                    | M   |     | FSO | **Xong** cho DW1 (`0135304b`)             |

## 4. Thông báo và push

**Đã có:** hộp thông báo trong app (mỗi nguồn báo một lần); web push
(`web_push.py`, `sw.js`, bật theo từng thiết bị); gửi qua Zalo; DW2 có thông
báo trong app.

**Còn thiếu**

| Việc                                                                                                       | Cỡ  | UAT | Ai       | Tình trạng 27/11                                                                                                                |
| ---------------------------------------------------------------------------------------------------------- | --- | --- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Chỉ làn nhắc việc của DW1 gửi push.** Push từ hàm `deliver` của nền tảng, có gom, cho mọi DW             | M   | ⚑   | FSO      | **Xong** (`04769aab`): mọi thông báo đẩy tới thiết bị đã bật, làn `web_push_delivery`, một tag                                  |
| Đăng xuất thì hủy đăng ký push của thiết bị                                                                | S   |     | FSO      | **Xong** (`e3e9c891`); phiên hết hạn không đăng xuất: Sales 78 còn ghi                                                          |
| Thư chuyển cho Sales thì push                                                                              | S   |     | DW1      | **Xong** (`04769aab` + nhắc `your_turn`): thư mở hoặc đẩy hồ sơ tới lượt PIC thì push; kiểm lại ở UAT với thư chỉ nằm ở Hộp thư |
| Tùy chọn từng người: loại nào báo, giờ im lặng, bật/tắt push từng loại                                     | M   |     | FSO      | ticket 16                                                                                                                       |
| Bản tin buổi sáng cho DW2 (DW1 đã có)                                                                      | M   |     | DW2      | **Xong** từ trước (`a6924ee3`, `dw_purchasing/domain/brief.py`)                                                                 |
| iPhone thật ở UAT: chứng chỉ HTTPS iPhone tin, máy chủ ra được `web.push.apple.com`, `DW_WEB_PUSH_SUBJECT` | S   | ⚑   | Đạt + IT | Sales 48/83, chờ Đạt + IT                                                                                                       |

## 5. Nhận và gửi thư

**Đã có**

- Nhận: Power Automate → SharePoint → máy sync → thư mục `.eml`; mỗi người một
  thư mục; DW nào đọc thư của ai do trang Thành viên quyết; làn
  `sales_mail_drop` / `purchasing_mail_drop` mỗi phút đọc file chưa có trong sổ
  (`mailbox_files`), một thư ở hai thư mục chỉ lưu một lần.
- Gửi: thư mục outbox + flow thứ hai gửi từ hộp thư của chính người dùng
  (`outbox_folder.py`); DW1 gửi bản nháp kèm file; DW2 gửi RFQ **không kèm file**;
  cả hai theo dõi `queued`/`sent`/`failed` và báo người.

**Còn thiếu**

| Việc                                                                                                    | Cỡ      | UAT | Ai  | Tình trạng 27/11                                                            |
| ------------------------------------------------------------------------------------------------------- | ------- | --- | --- | --------------------------------------------------------------------------- |
| **Watchdog**: thư mục của một người không có thư mới quá N giờ làm việc → báo admin (flow chết im lặng) | S–M     | ⚑   | FSO | ticket 01 (`DwLaneStale` chỉ thấy làn dừng, không thấy flow một người chết) |
| Dựng flow gửi cho từng người ở Proterial, đo đầu-cuối                                                   | S/người | ⚑   | Đạt | Sales 23/83, chờ Đạt ở Proterial                                            |
| Trả lời **trong cùng luồng thư** của khách (In-Reply-To): hiện mỗi lần gửi là một thư mới               | M       |     | FSO | ticket 36, chờ Đạt đo flow trả lời (đo cùng Sales 23)                       |
| Bản nháp do model viết gửi được bằng "Gửi từ hộp thư của tôi" (hiện chỉ `mailto:`/chép)                 | M       |     | DW1 | **Xong** (`1e867f0c`, Sales 76)                                             |
| DW2: RFQ kèm bản vẽ, spec                                                                               | S–M     |     | DW2 | ticket 30                                                                   |
| Thân thư HTML và chữ ký                                                                                 | S       |     | FSO | HTML đã có (`outbox_folder.py:46`); chữ ký: ticket 25                       |
| Thời hạn lưu thư DW1 (làn xóa như DW2 `retention.py`) — **Đạt quyết số ngày**                           | S       |     | FSO | Sales 84, chờ Đạt (số ngày và luật giữ thư)                                 |
| Trang admin: trạng thái từng hộp thư (có thư mục, thư cuối, biên nhận cuối)                             | M       |     | FSO | ticket 03                                                                   |

Giới hạn Power Automate bản thường (Microsoft 365): 6.000 lượt gọi/người/ngày;
Outlook 300 lượt/phút; thư ≤ 49 MB; không connector premium; flow không chạy
90 ngày có thể bị tắt, lỗi liên tục 14 ngày thì bị tắt. Với 6 PIC, giới hạn số
lượng không chạm; rủi ro thật là **flow chết im lặng**, nên watchdog ở trên.

Vì sao không ghi thẳng xuống ổ đĩa máy chủ: flow chạy trên cloud; ghi vào ổ đĩa
trong LAN cần connector File System (premium) và on-premises data gateway (admin
M365 cài), Proterial không có cả hai (`infra/onprem/README.md`). Nếu sau này có,
chỉ thay cách thư vào thư mục; làn đọc thư giữ nguyên.

## 6. Bravo gateway (`apps/bravo-gateway`, `packages/python/dw_bravo`)

**Đã có:** HTTP/JSON trong mạng Docker nội bộ, lệnh có kiểu và phiên bản
(`dw_bravo.contract`); 6 lớp kiểm (vé Ed25519, user còn hoạt động, quyền Bravo,
luật màn hình từ XML, khóa chứng từ, ghi + đọc lại); sổ `bravo.write_ledger`;
công tắc theo tenant; theo dõi Bravo đổi (fingerprint). Lệnh ghi:
`so.line.set_confirmed_date`, `so.line.set_quantity` (viết xong);
`so.line.cancel`, `so.line.split`, `so.create` (`pending`). Lệnh đọc: chỉ
`sync.changes`, còn lại trả 501. Màn hình: chỉ `EDIT_BizDocSO`.
Đến 27/11: `so.line.cancel` viết xong (công tắc vẫn tắt tới khi có bằng chứng
UAT); `so.line.split`, `so.create` vẫn `pending` (`dw_bravo/contract.py`);
mỗi lần ghi kết thúc bằng `CreateProcess`; hai Bravo đích UAT/thật chọn trên
trang quy tắc (Sales 85).

**Còn thiếu** (chi tiết ở ticket Sales 63, 70–75)

| Việc                                                                                                                                                           | Cỡ  | UAT | Ai  | Tình trạng 27/11                                                                                                                                  |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- | --- | --- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cho lưu SO có sẵn: `context_event` vẫn trống dù đã trace "Edit" (ticket 70)                                                                                    | S   | ⚑   | Đạt | **Xong** (`82ea1b73`, Sales 70)                                                                                                                   |
| Hủy dòng SO từ trace 26/11 (71)                                                                                                                                | M   | ⚑   | Đạt | Code **xong** (`7b350468`, `361bab56`, `8bdd141c`, `214b86d6`); bật công tắc chờ bằng chứng UAT (Sales 71/52)                                     |
| Tạo SO: dòng mới lấy giá trị từ danh mục hàng theo grid 8213 + luật `CartonSize='-'` (72)                                                                      | M   |     | Đạt | Một phần (`1c40d8c6`, `5815266a`, `208c6622`); đường pipeline và `pending` chờ thủ tục đọc trực tiếp (Sales 50) và lần tạo trên UAT (Sales 72/52) |
| Tách dòng (73), đổi đơn giá: cần một buổi trace UAT                                                                                                            | M   |     | Đạt | Tách: code xong (`e37b19d2`), chờ trace tách sạch trên UAT (Sales 73/52); đổi đơn giá: chờ trace (Sales 52 mục G)                                 |
| Gọi `usp_B30BizDocProcess_CreateProcess` sau mỗi lần ghi như client Bravo (74) — **Đạt quyết**                                                                 | M   | ⚑   | Đạt | **Xong** (`22975464`, Sales 74, theo khuyến nghị)                                                                                                 |
| Quyền lệnh Bravo (`B00Permission`: user, role, `NoInherit`) — đang trả "không rõ" nên từ chối hết (75)                                                         | M   | ⚑   | Đạt | Code **xong** (`0f70cedf`); chờ IT chạy script 10 trên UAT (Sales 75)                                                                             |
| IT tạo 2 login trên UAT (script 08), chạy script 07 (trigger ghi sang `<db>_Log`)                                                                              | S   | ⚑   | IT  | Sales 63/85, chờ IT (thêm chạy lại script 08)                                                                                                     |
| Các lệnh đọc còn lại: khách, hàng, quy đổi, tra báo giá (ticket 50)                                                                                            | L   |     | FSO | Sales 50 (bản sao theo rowversion đã có; còn các kiểu đọc này và thủ tục gọi trực tiếp)                                                           |
| Replay hằng đêm các lần lưu đã ghi lại; trang theo dõi; thêm màn DW2 (ticket 65)                                                                               | L   |     | FSO | ticket 02 (watch theo Bravo đang dùng + trang), 26 (replay), 31 (màn DW2)                                                                         |
| **Lệnh của DW2** (W11–W18): tạo/sửa PR, tạo PO từ PR, duyệt PR (`usp_B30AccDoc_ApprovalVouchers`); bản ghi UAT 26/11 đã có các thao tác này, thiếu sửa ngày PO | L   |     | DW2 | ticket 31 → 32 → 33; sửa ngày PO chờ trace UAT                                                                                                    |
| Nâng client gateway và vé duyệt (`bravo_gateway_client.py`, `BravoWriteStamp`) ra khỏi `dw_sales`                                                              | M   |     | FSO | ticket 04                                                                                                                                         |

**DW2 cắm vào gateway**, theo đúng đường DW1 đã đi:

1. Thêm lệnh vào `dw_bravo.contract` (kiểu, phiên bản, màn hình, bảng), để
   `pending` tới khi trace UAT khớp.
2. Thêm bảng màn DW2 vào `statements.SCREENS` và khóa công tắc (ví dụ `po.` →
   `purchasing_bravo_writes`) vào `SWITCH_KEYS`. Công tắc tắt mặc định; bật bằng
   phiên bản quy tắc của tenant có `uat_proof`.
3. Phía DW2: port trong `dw_purchasing.application`, adapter HTTP (dùng client
   chung sau khi nâng); loại phê duyệt `bravo_write.<chứng từ>` do chính người
   có user Bravo duyệt, kèm vé ký.
4. Trace một lần lưu tay của người dùng trên UAT cho mỗi lệnh; khớp từng cột
   thì mới bật.

**Không DW nào tự nối SQL Server**: import driver ngoài `apps/bravo-gateway`
làm CI đỏ. Trong lúc chờ, DW2 vẫn xuất file import Bravo
(`dw_purchasing/adapters/bravo_file.py`).

## 7. Các phần khác

| Phần                         | Đã có                                                                 | Còn thiếu                                                                                                      | Cỡ  | UAT | Ai      | Tình trạng 27/11                                                                                                              |
| ---------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --- | --- | ------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Định danh (Keycloak ↔ AD)    | Liên kết theo mã nhân viên (`dw_sales/application/identity_links.py`) | Nâng lên nền tảng (DW2 cũng cần mã nhân viên → user Bravo); trang admin; chờ AD của Proterial                  | M   | ⚑   | FSO; IT | ticket 05 (nâng), 06 (trang admin); AD: Sales 64, chờ IT                                                                      |
| Đọc file khách trong sandbox | `apps/reader`, không mạng, một tiến trình mỗi file                    | Đường đính kèm từ chat (mục 1)                                                                                 | —   |     | —       | ticket 23                                                                                                                     |
| Quét virus                   | port ở `dw_platform`, ClamAV                                          | —                                                                                                              | —   |     | —       | —                                                                                                                             |
| Cửa gọi model                | `dw_agent_runtime`, kiểm bằng code, mọi bước có công tắc              | Chạy đo chứng thực trên model nhà máy (`--attest`)                                                             | M   | ⚑   | Đạt     | Sales 57, chờ Đạt trên máy nhà máy                                                                                            |
| Shadow mode                  | chỉ ở `dw_sales/application/shadow.py`                                | Nâng lên `dw_agent_runtime` trước khi DW2 có bước model                                                        | M   |     | FSO     | ticket 07                                                                                                                     |
| Artifact theo tenant         | `TenantOverlay` (prompt, skill, tool spec)                            | —                                                                                                              | —   |     | —       | —                                                                                                                             |
| Vận hành on-prem             | compose, backup, giám sát (`ops-hardening.md`)                        | Máy chủ nhà máy (Windows Server 2025 + VM Ubuntu), GPU cho Strata; runner CI cho deploy; CI trên `main` còn đỏ | L   | ⚑   | Đạt     | Sales 83/84, chờ Đạt (máy, GPU, runner, billing Actions); cảnh báo của DW tới mail đã có (`821ce89e`, `c9c062ea`, `4901f0b3`) |
| Môi trường dev               | `docs/dev/huong-dan-moi-truong-dev.md`                                | Góp ý từ lần chạy đầu của đội DW2                                                                              | S   |     | DW2     | chờ đội DW2                                                                                                                   |
