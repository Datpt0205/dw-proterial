# Phần dùng chung DW1–DW2: hiện trạng và việc còn lại

Dành cho đội DW1 và DW2. "Phần chung" là thứ nằm ở nền tảng hoặc package dùng
chung, cả hai DW đều dựa vào. **DW2 không viết lại bản của mình**: mỗi sự thật
một chủ (`CLAUDE.md`). Cần khác đi thì sửa ở chỗ chung, hoặc khai một Protocol
ở phía DW2 và để composition root nối.

Cột "Đề xuất người làm" là đề xuất, chốt trong buổi họp. Trạng thái lấy từ
`.claude/plans/` ngày 2026-11-26.

---

## 1. Danh sách

| #   | Phần chung                                                                 | Ở đâu                                                                                                                                                 | Hiện trạng                                                                                                                                                                               | Việc còn lại                                                                                                                                                         | Đề xuất người làm                             |
| --- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1   | **Nhận thư** (Power Automate → SharePoint → máy sync → thư mục `.eml`)     | `infra/onprem/README.md` "Mail without access to Microsoft 365"; làn `sales_mail_drop`, `purchasing_mail_drop`; `dw_platform.application.drop_folder` | Chạy được, đo trên máy Đạt (1 phút 20 giây/thư). Một flow cho cả hai DW; DW nào đọc thư của ai do **trang Thành viên** quyết (scope `sales.inbox.process` / `purchasing.request.intake`) | Chạy thật trên máy nhà máy; watchdog cho phiên Windows của máy sync; **thời hạn lưu thư** (anh Đạt quyết)                                                            | Đạt                                           |
| 2   | **Gửi thư từ hộp thư của chính người dùng** (thư mục outbox, flow thứ hai) | `infra/onprem/README.md` "Sending mail…"; `dw_platform.application.outbox_folder`; làn `sales_outbound`, `purchasing_outbound`                        | Đã làm, **chưa dựng ở Proterial**                                                                                                                                                        | Dựng flow gửi cho từng người khi Proterial ký; đo đầu-cuối                                                                                                           | Đạt dựng; DW2 thử luồng RFQ                   |
| 3   | **Bravo gateway** (đọc/ghi Bravo)                                          | `apps/bravo-gateway`, `packages/python/dw_bravo`; ADR `docs/adr/0027-…`                                                                               | Chạy offline và trên SQL Server thử; ghi SO (DW1) đang **tắt** chờ UAT                                                                                                                   | IT tạo 2 login trên UAT (script 08), script 07; quyền lệnh Bravo; bước `usp_B30BizDocProcess_CreateProcess` sau mỗi lần lưu; **thêm loại lệnh của DW2** (mục 3 dưới) | Đạt (gateway); DW2 (lệnh và màn hình của DW2) |
| 4   | **Chạy luật màn hình Bravo** (XML layout)                                  | `dw_bravo.runner` (ticket 59)                                                                                                                         | Màn SO chạy offline; trace UAT 25/11 đã có tạo SO, tách dòng, hủy dòng (còn thiếu đổi đơn giá)                                                                                           | Trace các màn DW2 sẽ ghi: trace UAT 26/11 đã có tạo PR, sửa PR, tạo PO từ PR, duyệt PR; còn thiếu sửa ngày PO                                                        | DW2 trace, Đạt hỗ trợ runner                  |
| 5   | **Đọc dữ liệu Bravo / đồng bộ theo rowversion**                            | `dw_bravo.sync`, read `sync.changes` (ticket 50)                                                                                                      | Có; phần kiểm tra còn chờ                                                                                                                                                                | Danh mục bảng/cột DW2 cần đọc (R20–R35 trong file yêu cầu API)                                                                                                       | DW2 liệt kê, Đạt cấp quyền đọc                |
| 6   | **Theo dõi Bravo đổi** (layout, trigger, cột)                              | ticket 65; `GET /v1/fingerprint`                                                                                                                      | Có watch, chưa có replay hằng đêm                                                                                                                                                        | Thêm màn DW2 vào danh sách theo dõi                                                                                                                                  | Đạt                                           |
| 7   | **Định danh**: Keycloak nối AD, neo theo mã nhân viên                      | ticket 64; ADR 0027 mục 5                                                                                                                             | Có liên kết; **chờ AD** của Proterial                                                                                                                                                    | Trả lời của IT về AD                                                                                                                                                 | Đạt                                           |
| 8   | **Đọc file khách trong sandbox**                                           | `apps/reader` (+ `reader-gateway`), ticket 25                                                                                                         | Có, dùng chung                                                                                                                                                                           | —                                                                                                                                                                    | —                                             |
| 9   | **Quét virus**                                                             | port malware trong `dw_platform`, container `clamav`                                                                                                  | Có (đã dời về nền tảng 11-01)                                                                                                                                                            | —                                                                                                                                                                    | —                                             |
| 10  | **Cửa gọi model** (một lần gọi, có kiểm)                                   | `dw_agent_runtime` (`InterpretationPort`, `caller_run`, `figure_check`)                                                                               | Có (dời về nền tảng 11-01)                                                                                                                                                               | Chạy chứng thực trên model nhà máy                                                                                                                                   | Đạt                                           |
| 11  | **Phê duyệt / HITL**                                                       | `ApproveAndResumeService`, `decision_guards`, `decision_stamps` (nền tảng)                                                                            | Có                                                                                                                                                                                       | —                                                                                                                                                                    | —                                             |
| 12  | **Thông báo, push iPhone**                                                 | ticket 48                                                                                                                                             | Có                                                                                                                                                                                       | iPhone tin chứng chỉ portal, host tới `web.push.apple.com`, `DW_WEB_PUSH_SUBJECT`                                                                                    | Đạt                                           |
| 13  | **Khung chat**                                                             | `@dw/ui` `AssistantChat` (Ant Design X)                                                                                                               | Có; Sales có thêm widget "Hỏi DW1" (11-26)                                                                                                                                               | Đưa vỏ widget lên `@dw/ui` nếu DW2 cũng muốn widget (đang nằm trong `app/sales`)                                                                                     | DW2 quyết, Đạt chuyển                         |
| 14  | **Shadow cho bước model đang tắt**                                         | ticket 67, hiện ở `dw_sales`                                                                                                                          | Chỉ DW1                                                                                                                                                                                  | Nếu DW2 cần: tách phần chung lên nền tảng, không chép                                                                                                                | Bàn khi DW2 có bước model                     |
| 15  | **Artifact theo tenant** (prompt, skill, tool spec)                        | `dw_kernel.overlay.TenantOverlay`                                                                                                                     | Có                                                                                                                                                                                       | —                                                                                                                                                                    | —                                             |
| 16  | **Vận hành on-prem** (deploy, backup, giám sát, model)                     | `.claude/plans/ops-hardening.md`, `infra/onprem/README.md`                                                                                            | Đang làm                                                                                                                                                                                 | —                                                                                                                                                                    | Đạt                                           |
| 17  | **Môi trường dev**                                                         | `docs/dev/huong-dan-moi-truong-dev.md`                                                                                                                | Có (11-26)                                                                                                                                                                               | Góp ý từ lần chạy đầu của đội DW2                                                                                                                                    | Đội DW2 góp ý                                 |

---

## 2. DW "được kích hoạt" khi có thư thế nào

Đúng như anh Hoa nói: Proterial chỉ cho dùng **Power Automate thường**, nên thư
phải thành file nằm ở một chỗ DW đọc được. Cụ thể:

```
Outlook của người dùng ─flow PA (connector chuẩn)─► thư viện SharePoint của Team "DW - chuyen thu"/DW-mail/<email>
  ─OneDrive sync─► máy Windows trong nhà máy ─SMB chỉ đọc─► worker DW
```

- **Không có "trigger" đẩy vào DW.** Worker **hỏi thư mục mỗi phút** (làn
  `purchasing_mail_drop` cho DW2, `sales_mail_drop` cho DW1), đọc mỗi file một
  lần, lưu vào Postgres. API không bao giờ đọc thư mục.
- **Vì sao không lưu thẳng xuống ổ đĩa máy chủ:** flow Power Automate chạy trên
  cloud. Ghi xuống ổ đĩa trong LAN cần connector **File System** (premium, phải
  mua license) và **on-premises data gateway** (admin M365 cài và đăng ký vào
  tenant). Proterial không có premium, admin ở Nhật đã từ chối mọi quyền M365
  (27/10). Đường SharePoint chỉ dùng connector chuẩn, người dùng tự đăng nhập,
  máy sync chỉ gọi ra ngoài, và SharePoint giữ thư khi máy DW tắt.
- **Đổi đường sau này không đụng DW:** nếu Proterial cho gateway hoặc Graph API
  thì chỉ thay cách thư vào thư mục (hoặc bỏ thư mục); làn đọc thư giữ nguyên.
- Thời gian đo: 1 phút 20 giây khi file do chính tài khoản sync ghi; 11 phút 29
  giây khi do flow của người khác ghi (OneDrive kéo file người khác chậm, đo 1 lần).

---

## 3. Bravo gateway với DW2

**Dạng gì:** hai chặng.

1. **DW1/DW2 → gateway: HTTP/JSON trong mạng nội bộ Docker** (`dw-bravo`,
   không mở cổng ra ngoài). Không phải REST tự do: chỉ có **lệnh định kiểu, có
   phiên bản** trong `dw_bravo.contract` (JSON Schema:
   `contracts/jsonschema/bravo_gateway.json`).
    - `POST /v1/reads` — đọc (loại chưa hỗ trợ trả 501)
    - `POST /v1/writes` — ghi, kèm **vé duyệt có chữ ký** (Ed25519)
    - `POST /v1/writes/preview` — kiểm 1–5 và hiện câu SQL sẽ gửi, không gửi
    - `GET /v1/fingerprint/{uat|production}` — cho việc theo dõi Bravo đổi
2. **Gateway → Bravo: SQL trực tiếp** vào SQL Server qua **2 login quyền tối
   thiểu** (đọc: SELECT theo cột; ghi: INSERT/UPDATE theo cột). Không stored
   procedure, view, bảng hay job nào của DW trong DB Bravo. Gateway gửi đúng
   câu `UPDATE … WHERE Id=… AND timestamp=…` client Bravo gửi, dưới context của
   **user Bravo của người duyệt**, sau 6 lớp kiểm (vé, user còn hoạt động, quyền
   Bravo đọc trực tiếp, luật màn hình, khóa chứng từ, rồi ghi và đọc lại đối chiếu).

**Không DW nào tự nối SQL Server.** Import hay khai driver ngoài
`apps/bravo-gateway` làm CI đỏ.

**DW2 cắm vào gateway thế nào** (theo đúng đường DW1 đã đi):

1. Thêm lệnh của DW2 (W11–W18 trong file yêu cầu API 13/11) vào
   `dw_bravo.contract`: kiểu, phiên bản, màn hình, bảng; để `pending` cho tới
   khi trace UAT.
2. Thêm bảng của màn DW2 vào `statements.SCREENS` của gateway, và khóa công tắc
   (ví dụ tiền tố `po.` → rule key `purchasing_bravo_writes`) vào `SWITCH_KEYS`.
   Công tắc tắt mặc định; bật bằng phiên bản rules của tenant có `uat_proof`.
3. Phía DW2: khai port trong `dw_purchasing.application`, adapter HTTP giống
   `dw_sales/adapters/bravo_gateway_client.py`; loại phê duyệt
   `bravo_write.<chứng từ>` do chính người có user Bravo duyệt, với decision
   stamp ký vé (như `BravoWriteStamp` của DW1).
4. Trace một lần lưu tay của PIC trên UAT cho mỗi loại lệnh; khớp từng cột thì
   mới bật.

Trong lúc chờ: DW2 vẫn xuất **file import Bravo** (`dw_purchasing/adapters/bravo_file.py`)
để người nhập.
