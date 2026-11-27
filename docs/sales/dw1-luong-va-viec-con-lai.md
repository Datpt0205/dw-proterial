# DW1: luồng nên có, và việc còn lại tới UAT và production

Dành cho anh Đạt, đội DW1 và đội hỗ trợ. Tài liệu này không chép lại luồng
của BA (WIV-03-012 đơn hàng, WIV-03-023 báo giá, đã mã hóa trong
`packages/python/dw_sales/src/dw_sales/domain/process.py`). Nó hỏi: **với
nghiệp vụ đó, mỗi bước nên chạy thế nào để người dùng làm ít nhất, ở một chỗ.**
Hiện trạng đọc từ code ngày 2026-11-26; số ticket trỏ vào
`.claude/plans/sales/dw1-production/issues/`.

---

## 1. Nguyên tắc

1. **Mỗi vai một kênh.** Không bắt ai nhảy qua lại giữa thư, chat, portal và
   Bravo trong cùng một việc.
2. **DW làm, người quyết.** Bước dễ và hoàn tác được thì DW tự chạy (có đo tỉ
   lệ lỗi và audit, ADR 0015); bước ghi Bravo hoặc gửi ra ngoài thì người bấm
   duyệt, một lần.
3. **Gửi từ DW, đi bằng hộp thư của chính người dùng** (outbox + Power
   Automate). Không "chép thư, sang Outlook, quay lại bấm đã gửi".
4. **Không gõ lại thứ DW đã biết**: số SO, ngày PC, Design đã xong.
5. **Có việc thì được báo**: ai tới lượt thì có push, không phải tự đi tìm.

### Kênh của từng vai

| Vai                            | Kênh duy nhất                                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Sales PIC                      | **Việc của tôi** (`/sales`, cài như app, push về iPhone). Mở một việc ra: đề xuất của DW, các nút, và chat của chính hồ sơ đó. |
| Trưởng phòng Sales / Manager   | Việc của tôi, có push: duyệt, giao lại người, ngay tại chỗ.                                                                    |
| Người kiểm chéo, PIC xuất khẩu | Việc của tôi, có push (ticket 78; đơn thiếu NOC/ESF báo PIC xuất khẩu, chưa ai có quyền thì báo Trưởng phòng).                 |
| Khách hàng                     | Thư, từ hộp thư của PIC.                                                                                                       |
| PC, Design                     | Thư như hôm nay; Design vẫn làm trên Bravo. Không bắt họ dùng thêm một cổng.                                                   |
| Bravo                          | Không ai phải vào Bravo để làm lại việc DW đã làm: DW ghi qua gateway dưới user của người duyệt (ADR 0027).                    |

**Chat hay nút?** Ticket 48 ghi "chat chỉ để hỏi", còn ticket 56 (Đạt 11-20)
ghi "chat của hồ sơ là kênh chính". Đề xuất: **cả hai trong một mục** của Việc
của tôi; nút và câu trong chat gọi cùng một lệnh (phần chung đã có:
`useCaseChatOffers`). Mục đơn hàng và báo giá trong Việc của tôi có nút "Hỏi DW1
về hồ sơ này" mở chat của chính hồ sơ, với các nút của trang (ticket 79, 27/11).

---

## 2. Luồng đơn hàng (PO → SO)

| #   | Bước                                 | DW tự làm                                                     | Vướng hôm nay                                                                              | Nên làm                                                                                                           | Ticket     |
| --- | ------------------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | ---------- |
| 1   | Nhận thư / PO                        | Đọc hộp thư, phân loại, giao PIC theo khách, mỗi PO một hồ sơ | Thư DW chuyển cho Sales **không được push**; thư báo "PO đã lên cổng khách" không tạo việc | Push thư được chuyển; thư báo PO trên cổng tạo việc "Tải PO lên" có ô tải ngay trong việc                         | 78         |
| 2   | Đọc PO, đổi mã, kiểm LME, so báo giá | Đọc, đổi mã, kiểm, ghi lý do từng dòng                        | PO có mật khẩu: **mọi ô bị gắn cờ, 225 dòng phải bấm từng dòng**; việc không có ô chọn mã  | Xác nhận theo ngoại lệ: chỉ dòng trượt kiểm mới phải bấm, còn lại một nút; ô chọn mã ngay trong việc              | 80, 79     |
| 3   | Thiếu mã → nhờ Design tạo            | Soạn thư kèm mã gần nhất                                      | Chép thư → Outlook → quay lại ghi đã gửi; nhắc việc nhắc PIC chứ không nhắc Design         | Một nút "Gửi Design" (người nhận từ cấu hình tenant); mã mới xuất hiện trong bản sao Bravo thì DW tự gán vào dòng | 77         |
| 4   | Hỏi PC ngày giao                     | Soạn bản hỏi, nhắc sau 24 giờ                                 | **5 thao tác, 2 kênh**: chép, Outlook, ghi đã hỏi, mở thư PC, bấm đọc, ghi ngày            | Một nút "Gửi PC"; DW tự đọc thư PC trả lời (có số PO) và điền ngày; PIC chỉ bấm [Đúng]/[Sửa]; nhắc thẳng PC trước | 77         |
| 5   | Ngoại lệ (blacklist, ECP, NOC/ESF…)  | Phát hiện, hỏi trong chat hồ sơ                               | Blacklist/ECP/LME chưa nối bản sao Bravo; PIC xuất khẩu không được push                    | Nối ba kiểm vào bản sao Bravo; thêm người nhận NOC/ESF vào danh sách "tới lượt"                                   | 50, 78     |
| 6   | Đề nghị khách sửa PO                 | Soạn thư                                                      | Bản nháp sửa **không gửi được qua outbox** (chỉ 2 loại được gửi)                           | Mọi bản nháp gửi khách đều gửi được; gửi xong tự ghi trạng thái                                                   | 76         |
| 7   | Nhập Bravo                           | Hôm nay: dựng file dán                                        | Tải file, dán vào Bravo, **gõ lại số SO**, xuất Bravo ra Excel để đối chiếu                | Một nút "Nhập vào Bravo": gateway ghi dưới user của PIC, đọc lại, tự điền số SO                                   | 70–75, 51  |
| 8   | Kiểm chéo                            | Đọc lại SO, so từng dòng                                      | **Duyệt hai lần cùng một nội dung**; người kiểm cùng cấp không được báo                    | Đọc lại khớp thì qua; người kiểm chỉ nhận đơn chênh lệch, ngoại lệ, hoặc mẫu audit (cần Đạt + Proterial quyết)    | 81, 78     |
| 9   | Gửi xác nhận cho khách               | Soạn thư kèm PO và Excel đã xử lý                             | Phải bấm "ghi đã gửi" trước rồi mới được "gửi"                                             | Một nút "Gửi xác nhận"; biên nhận gửi tự ghi trạng thái                                                           | 76         |
| 10  | Khách đồng ý / im lặng               | Đếm ngày im lặng                                              | PIC bấm ghi tay một việc DW đã biết                                                        | DW tự ghi "đồng ý" (thư khách đọc ra đồng ý, có trích dẫn) hoặc "im lặng = đồng ý", báo PIC, có nút hoàn tác      | 82         |
| 11  | Thay đổi sau xác nhận                | Đọc yêu cầu đổi, so từng dòng                                 | Vòng PC vướng như bước 4; hủy và tách dòng chưa ghi được Bravo                             | Như bước 4; hủy dòng (đã trace 26/11), tách dòng                                                                  | 77, 71, 73 |

## 3. Luồng báo giá (RFQ → báo giá)

| #     | Bước                   | Vướng hôm nay                                                                                                      | Nên làm                                                                                                                                 | Ticket     |
| ----- | ---------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Q1    | Nhận RFQ, mở hồ sơ     | Người tự chọn mass/pcs; hàng pcs Sales tự đi xin giá GM                                                            | DW đề xuất mass/pcs; thư hỏi GM gửi một nút                                                                                             | 05         |
| Q2    | Tạo YCBG               | DW soạn, **PIC gõ lại vào Bravo** rồi ghi số                                                                       | DW tạo YCBG qua gateway khi PIC bấm                                                                                                     | 68         |
| Q3    | Gửi Design             | Chép thư, sang Outlook, quay lại ghi                                                                               | Một nút qua outbox                                                                                                                      | 77         |
| Q4    | Design trả lời         | Design điền Bravo, nhưng **PIC xuất màn YCBG ra Excel rồi tải lên**                                                | Bản sao Bravo thấy YCBG `CLOSE` thì tự chuyển bước và push PIC                                                                          | 50, 58     |
| Q5/Q6 | Từ chối, trao đổi spec | Bản nháp không gửi được qua outbox                                                                                 | Gửi một nút                                                                                                                             | 76         |
| Q7    | Giá                    | Bravo tính giá, nhưng PIC tự nhập phiếu báo giá                                                                    | DW tạo báo giá qua gateway; giá do luật màn hình Bravo tính; PIC xác nhận                                                               | 68         |
| Q8/Q9 | Tài liệu và duyệt      | **Tới 4 lần duyệt**: kiểm, Manager, ký giấy, quét rồi tải bản ký lên; Manager chỉ được push nếu có quyền giao việc | QN không ký; QM/QS: Manager duyệt một lần trên DW, có push; PDF dựng từ bản ghi Bravo; bản ký đóng bước khi DW thấy thư gửi có đính kèm | 39, 58, 78 |
| Q10   | Gửi khách              | Chưa có flow gửi cho từng PIC                                                                                      | Flow Power Automate cho từng PIC                                                                                                        | 23, 83     |
| Q11   | Master list            | PIC tự ghi                                                                                                         | Đọc từ Bravo                                                                                                                            | 12         |

---

## 4. Thao tác ngay tại chỗ (trong việc hoặc trong chat)

**Đã có:** hỏi trạng thái, việc của tôi, việc quá hạn; quyết một cờ; đề xuất đổi
ngày hoặc số lượng dòng SO để ghi Bravo; gợi ý soạn trả lời/nhắc khách (trỏ về
nút của trang); quyết đơn và báo giá trong Việc của tôi; từ chối mã gợi ý;
trưởng phòng giao hồ sơ bằng một câu trong chat ("giao cho Diệu", 79); chat của
hồ sơ mở ngay từ mục trong Việc của tôi; chọn mã PRV ngay trong mục đơn hàng,
từng dòng một (79).

**Còn thiếu**, xếp theo mức giảm việc cho người dùng (ticket 79 trừ khi ghi khác):

1. Gửi thư cho khách, PC, Design từ việc hoặc từ chat, một bấm (76, 77).
2. Duyệt / trả lại ngay trong chat: kiểm chéo, Manager, ghi Bravo, phiên bản quy tắc.
3. ~~Giao người ngay trong chat~~ (xong 26/11).
4. ~~Chọn/xác nhận mã PRV ngay trong việc~~ (xong 27/11: tối đa 5 dòng trong việc, còn lại mở hồ sơ).
5. Chấp nhận ngày PC do DW đọc, một bấm (77).
6. Ghi khách đồng ý, đóng hồ sơ có lý do, đề nghị khách sửa từ chat.
7. Cờ của báo giá trong chat; bước tự chạy có nút hoàn tác trong chat.
8. "Xem trong thư" ngay trong việc; tắt push khi đăng xuất.

---

## 5. Việc còn lại của DW1

### 5a. Cần cho UAT

| Ticket | Việc                                                     | Đang chặn                                                             | Hướng làm                                                                                              |
| ------ | -------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **70** | Gateway: cho lưu SO có sẵn (`EDIT_BizDocSO\|Edit`)       | không (đã trace 25/11)                                                | Điền `context_event`, replay từ trace 2 và 3                                                           |
| **71** | Gateway: hủy dòng SO                                     | không (đã trace 26/11)                                                | Xong offline 26/11: lệnh, replay, đề xuất từ trang đơn và chat; công tắc tắt tới khi có bằng chứng UAT |
| **72** | Gateway: tạo SO, dòng mới lấy giá trị từ layout          | không                                                                 | Runner áp `bindingMembers` của grid 8213 và luật `CartonSize='-'`                                      |
| **73** | Gateway: tách dòng                                       | một lần tách sạch trên hàng cuộn ở UAT                                | Viết lệnh từ trace 26/11; bật khi có bằng chứng                                                        |
| **74** | Gateway: gọi `usp_B30BizDocProcess_CreateProcess`        | **Đạt quyết**                                                         | Đề xuất: gọi, cấp EXECUTE riêng thủ tục này, sửa ADR 0027                                              |
| **75** | Gateway: quyền lệnh Bravo                                | đo trên UAT (script 10 mới)                                           | Đọc `B00Permission` của một user, so với điều Bravo cho làm thật                                       |
| 52     | Đo trên UAT                                              | buổi ở nhà máy: đổi đơn giá, tách sạch, script 07, 08, 09, câu hỏi AD | Gom một buổi 30–45 phút với IT                                                                         |
| 63     | Gateway đạt acceptance 4                                 | 2 login của IT (script 08), script 07, 70–75                          | Sau 52 và 70–75                                                                                        |
| 51, 53 | Tạo SO, điều chỉnh SO qua gateway                        | 70–73                                                                 | 53: nút "Ghi vào Bravo" trên trang đơn đã có (26/11); 51: nối nút tạo SO                               |
| 50     | Bản sao Bravo và các kiểm dùng nó                        | login đọc của IT                                                      | Làm offline trước: blacklist, ECP, LME, "Design xong" từ `CLOSE`                                       |
| 68, 69 | DW nhập YCBG/báo giá; shadow việc ghi Bravo              | trace 10 phút; script 09                                              | Chạy chung buổi với 52                                                                                 |
| 64     | Một người nhiều tài khoản (AD)                           | AD của Proterial; trang admin                                         | Làm trang admin ngay                                                                                   |
| **76** | Gửi từ DW một bấm                                        | flow gửi (23) để chạy thật                                            | Mở mọi bản nháp gửi khách; "gửi rồi tự ghi"                                                            |
| **77** | Thư cho PC/Design qua outbox, DW tự đọc trả lời PC       | flow gửi (23)                                                         | Người nhận từ cấu hình tenant; làn đọc thư PC                                                          |
| **78** | Push cho người tới lượt                                  | không                                                                 | Push từ `deliver` của nền tảng; thêm người kiểm chéo, Manager, PIC xuất khẩu                           |
| **79** | Một chỗ làm việc: việc mở ra có chat và thao tác tại chỗ | không                                                                 | Thẻ trong chat: duyệt, giao người, chọn mã, nhận ngày PC                                               |
| 39     | Duyệt hai cấp báo giá                                    | không                                                                 | "Không duyệt", đơn tự chạy tiếp, câu chữ                                                               |
| 23, 48 | Flow gửi thư; push iPhone thật                           | hộp thư M365 để đo; IT: chứng chỉ, mạng ra `web.push.apple.com`       | Dựng một flow mẫu; hỏi IT                                                                              |
| **83** | Dựng DW1 cho UAT trên máy nhà máy                        | VM Ubuntu, Strata, flow thư từng PIC                                  | Theo `infra/onprem/README.md`; chạy `--attest`; viết lại bài walk e2e                                  |

### 5b. Cần cho production

| Ticket         | Việc                                       | Đang chặn                              | Hướng làm                                                                    |
| -------------- | ------------------------------------------ | -------------------------------------- | ---------------------------------------------------------------------------- |
| **80**         | Xác nhận theo ngoại lệ                     | Đạt lật lại quyết định 11-04           | Chỉ dòng trượt kiểm phải bấm; phần còn lại một nút; audit mẫu                |
| **81**         | Thiết kế lại kiểm chéo (O9)                | Đạt + Proterial                        | A: đọc lại khớp là qua (đề xuất); B: người kiểm trước khi ghi                |
| **82**         | Tự ghi khách đồng ý / im lặng, có hoàn tác | Đạt sửa ADR 0011                       | Bước nội bộ hoàn tác được, theo ADR 0015                                     |
| **84**         | Sẵn sàng production                        | runner CI, thanh toán GitHub, ruleset  | Diễn tập khôi phục backup, giám sát, thời hạn lưu thư DW1, CI xanh trên main |
| 55, 54         | Luồng theo spec 20/11; phản hồi cho BA     | BA                                     | Làm phần đã quyết 11-20                                                      |
| 58             | Loại báo giá và chữ ký                     | trường đánh dấu hàng đặc biệt (BA), 50 | Đóng bước ký bằng thư gửi đi                                                 |
| 04, 05, 12     | Màu/workbook mã; JP&HQ và pcs; master list | Proterial xác nhận; thư mẫu GM         | Làm khi có dữ liệu                                                           |
| 44, 46, 47, 56 | Bước tự chạy; chat và trang Hôm nay        | điểm đo từng bước                      | Theo 79                                                                      |
| 61, 62         | Stage theo phiên bản; vì sao dòng đi vậy   | mã BR-* của BA                         | Sau UAT                                                                      |

### 5c. Để sau

Ticket 40 (bước dùng skill, 0,800 dưới ngưỡng), 45 (llama.cpp thay Ollama),
15 (khách mới), Q12 trên dữ liệu thật, Flowable (chờ Đạt chọn a/b/c), RAG có
parser PDF/Word/Excel.

---

## 6. Cần anh Đạt quyết

1. **Chat và nút** cùng trong một mục của Việc của tôi (đề xuất ở mục 1).
2. **Kiểm chéo O9**: A (đọc lại khớp là qua) hay B (người kiểm trước khi ghi). Cần hỏi Proterial.
3. **Sửa ADR 0011**: DW tự ghi "khách đồng ý" có nút hoàn tác.
4. **Xác nhận theo ngoại lệ** thay cho bấm 225 dòng (lật lại quyết định 11-04).
5. **Thư nội bộ** (PC, Design) gửi qua outbox, người nhận chỉ lấy từ cấu hình tenant.
6. **Gateway gọi `CreateProcess`** sau mỗi lần ghi.
7. **Bước ký QM/QS**: bản ký giấy giữ nguyên (Đạt 11-02, không ký điện tử); chỉ bỏ việc quét rồi tải bản ký lên: DW đóng bước khi thấy thư gửi khách có đính kèm (ticket 58).
8. Bỏ thread agent; ngân sách độ trễ mỗi bước; Flowable a/b/c.

## 7. Proterial còn nợ

Danh bạ và PIC từng khách; thư mẫu; band LME; tồn kho từ PC; hồ sơ NOC; số ngày
im lặng theo từng khách; file nào thắng khi hai file một PO lệch nhau; một cặp
PO + SalesOrder thật cho mỗi khách; lead time từng mặt hàng; số thư mỗi ngày;
IT: 2 login (script 08), script 07, AD, chứng chỉ cho iPhone.
