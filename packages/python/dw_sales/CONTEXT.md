# Sales context (`dw_sales`) — glossary

DW1, Đơn hàng & Báo giá: a Sales department's order intake (WIV-03-012) and
quotation (WIV-03-023). The UI shows the Vietnamese labels below; code, the
API and the plan use the English terms. The spec is
`.claude/plans/sales/dw1-portal-demo/spec.md`. The decisions are in
`docs/adr/`, next to this file.

## Terms

- **Order case** (Hồ sơ đơn hàng): one customer PO number, from its first
  revision to confirmation. A later revision of the same PO joins the same
  case and supersedes the previous revision; it never opens a new case. A
  mail or a file with several PO numbers opens one case per PO number, every
  one on the same message; the inbox shows the mail once, with its cases
  (ticket 19).
- **Quote case** (Hồ sơ báo giá): one request for quotation, through to a
  sent quotation or a decline.
- **Quote for a PO** (Báo giá cho PO): a quote case a person opens from an
  order whose lines have no valid quotation (`quotation_missing`) with "Mở
  báo giá": the customer's, for those lines as the PO prints them, assigned
  to the order's PIC; DW1 never opens one by itself. The two cases name each
  other. While it is open the order **waits on the quotation** ("Đơn chờ báo
  giá") and cannot be prepared; once approved, those lines are checked again
  with its terms, which apply to that PO from its date ("Kiểm tra lại theo
  báo giá"); declined, the wait ends and the finding stays for Sales. One is
  open per order at a time (ticket 09).
- **Maker / checker** (Người làm / người kiểm): on an order, the makers are
  the preparer and whoever recorded the Bravo entry, in this round or an
  earlier one (a return, a revision, a change applied in Bravo), and whoever
  typed a value still on the case; the checker is the cross-checker. On a
  quote, the pricer and the approver. A checker is never a maker of the same
  case. Every one of them is named by their principal id.
- **Served source** (Đã mở nguồn): a page or sheet of a case's original that
  a person was shown, for one case version. Prepare and cross-check need the
  person's own record for the current version ("chưa mở nguồn" otherwise).
- **YCBG** (Phiếu yêu cầu báo giá): the quote-request form Sales enters in
  Bravo and sends to Design. Design's reply is matched by the YCBG number
  only. Bravo numbers it `RFQ` + yymmdd + `-` + nnn (`RFQ261110-002`), the
  only number Sales may record (ticket 16).
- **Design Check** (Kết quả Design trên Bravo): what Design writes on a YCBG
  line in Bravo, QUOTE with the BP code or DECLINE with a reason, the line's
  status then CLOSE. DW1 reads it back (from the YCBG export a person
  uploads until the vendor's API reads it) and records it on the one case
  waiting under the number; it moves no status and writes nothing to Bravo.
- **Check basis** (Căn cứ kiểm tra): what a check compared against, stamped
  on the case when the check ran. It is never re-read from master data.
- **Coverage statement** (Phạm vi đã kiểm): what was read and checked on one
  order ("Đã đọc N/N dòng …"); on a quote, as far as its reading records it
  (lines read, where, values a model read and how many are confirmed): a
  request's reader counts no printed rows, so no "N/N" is claimed.
- **Value correction** (Giá trị Sales sửa): the value Sales typed for one
  field a `value_uncertain` flagged, with who and when. It is kept beside the
  value as read, which stays the evidence; the order is entered, uploaded and
  confirmed with the corrected value. A line's number and the PO's number and
  revision are only confirmed as read, never changed.
- **Labelled case** (Kết quả người đã kiểm): one item a person decided on a
  model step's proposal: what the step proposed, what the person kept
  (confirmed as is, corrected to another value, or rejected), who and when,
  the versions that produced it, and the mail, case and line it was read from
  by reference. Written by the step's own service with the decision
  (dw_sales ADR 0015 decision 5, ticket 43). The share kept as proposed is
  the step's accuracy on real work; the cases set its threshold and teach it.
- **Decided line** (Dòng người đã quyết): a labelled case of the description
  reading whose newest decision on its line kept a code, with the line's
  description read back from its order. Shown to the next readings most
  like it, the same customer's first, as an example: the description and the
  kept item's attributes, never the code (ticket 43).
- **Prompt version** (Phiên bản lời nhắc): a tenant's version of a model
  step's prompt: the demonstrations every reading of the step is shown,
  proposed by DW1's optimiser only when it reads no decided line worse,
  more right, and passes the step's security cases; approved by the head,
  never by its proposer, never applied directly (ticket 43).
- **Delivery schedule** (Đợt giao): one delivery of a PO line's quantity, a
  quantity on a requested date, with where the PO prints it. A line printing
  one quantity and one date has one; a line the PO splits over several dates
  (rows under the line, or a "date: quantity" list in its date cell) has one
  per date, which must add up to the line's printed quantity
  (`line_total_mismatch` otherwise). The lead time is checked per schedule,
  the MOQ, pack and price per line; the upload file has a row per schedule
  (ticket 21). A split line's dates are asked of the customer, never typed.
  Sales confirms a split line per schedule, one date each, and the
  confirmation lists each schedule's quantity with its date (ticket 35).
  Once PC answered, a line's deliveries are PC's (below).
- **Request to PC** (Hỏi PC): the request Sales sends PC for an order's
  delivery dates, written by code from the case (each line asked: number,
  PRV code, the customer's code, quantity, requested date) in the hand-off
  copy (`sales_handoffs`, `pc_request`); the person copies it into Teams or a
  mail. DW1 sends nothing. "Ghi đã hỏi PC" puts the case **waiting on PC**
  (`pc_request`) until PC's answer is recorded for every line asked; the
  follow-up `waiting_pc` reminds the PIC meanwhile (ticket 07). Only before
  the order is in Bravo; in Bravo, PC's dates are the update loop's (ticket
  29).
- **PC's answer** (Ngày PC trả lời): per line, recorded by a person one line
  at a time, the line's deliveries with PC's dates: one for a line delivered
  at once; several for a line PC splits, whose quantities add up to the
  line's (a split that does not is refused, never adjusted); one per printed
  schedule for a line the PO splits. Each delivery is a row of the paste
  sheet and is confirmed with its own date. A re-confirmation by PC keeps the
  **first confirmed date** of each delivery (split anew: the line's earliest)
  and records the current one. A customer's change or a correction of the
  line's quantity or date drops it: PC is asked again (ticket 07).
- **Tenant version** (Phiên bản riêng): a customer's own version of a Sales
  rule or copy file (order and quote rules, pricing, KPI, e-mail and document
  copy, the Bravo upload template, the hand-off copy), proposed by a PIC or
  the head and approved by the head, never its proposer, on a `sales.rules`
  platform approval. It applies to that
  tenant only; a case keeps reading the version it stamped (tickets 19, 36).
- **Malware scan** (Quét mã độc): every attachment is scanned by ClamAV
  before anything reads it, then held to its name (ticket 25). An infected
  one routes its message to Sales (`malware_detected`) with nothing in it
  read or served; a scanner that cannot answer leaves the message not yet
  processed ("chưa quét được, thử lại"); a file that is not what its name
  says is refused unread. An encrypted file (an Office file or a PDF with a
  password) is not refused: it is marked "encrypted: contents not scannable
  by ClamAV" and read only inside the reader sandbox (ticket 17).
- **File with a password** (Tệp có mật khẩu): a PO file the customer locked
  with a password and wrote the password in the same mail. DW opens it in the
  reader sandbox with the candidates that one mail's text carries (each
  line's text after its last colon, then its words), the file itself telling
  which is right; no model guesses. The password is never stored, logged,
  audited or shown; the audit says only that the file was opened with a
  password from its own mail. Every value read from it is flagged
  `opened_with_password` ("Tệp có mật khẩu, cần xác nhận") for Sales. One
  none of the candidates opens routes its message `attachment_locked`.
- **Date to follow** (Ngày giao báo sau): a PO line printed with its
  requested date blank. It reads with no date and no schedule, and raises
  `requested_date_missing`: Sales asks the customer for the date, or goes
  ahead with it to follow, DW1 suggesting the first day the lead time allows
  (ticket 34).
- **Second file of a PO** (Tệp thứ hai của PO): two files of one mail naming
  the same PO number (a signed PDF and its Excel, ticket 22) are one PO and
  one case, compared value by value, lines matched by line number. The case
  holds its lines on the first file (the workbook beside a PDF, else the
  first attached), but **neither file wins**: each value they print
  differently is flagged `print_differs` (`value_uncertain`), typed by Sales
  or asked of the customer, and `files_disagree` names both values and both
  files. Which file should win is Proterial's to say (owed). Two files of
  one PO number that print other revisions or other line numbers, or three,
  route the mail to Sales.
- **Delivery term** (Điều kiện giao hàng): the Incoterms rule a sales order
  is entered on (DAP, FCA, CIP on the orders seen, one per customer). The
  upload file writes the customer's, from its record; a PO's own is read only
  where the customer's layout maps its label, kept as printed ("FCA
  Haiphong"), and compared by its rule: another one, or a term naming no
  single rule, raises `delivery_term_mismatch` for Sales to accept or ask
  about, never written over either side (ticket 02).
- **File-name revision hint** (Tên tệp gợi ý PO sửa): the suffix a file's
  name carries after the PO number (`R`, `R1`, `-2`, `-RE11`, `RV`), shown
  beside the PO number and the printed revision. Only a hint: the printed
  revision and the line comparison decide "PO sửa" (ticket 22).
- **PDF print** (Bản in PDF): a PDF print of a PO attached beside its
  workbook in the same mail. The two are one PO, read from the workbook; the
  print is kept as a second source, and a value it prints differently is
  flagged `print_differs` on the workbook's value (`value_uncertain`), never a
  second case (ticket 34).
- **Legacy encoding** (Font tiếng Việt cũ): Vietnamese typed in a TCVN3
  (`.VnTime`, `.VnArial`, …) or VNI (`VNI-Times`, …) font, whose letters are
  stored as other characters ("Cña hµng" for "Cửa hàng"). DW1 detects it by
  the font of a cell or a PDF text run, raises `legacy_encoding` and matches
  nothing on that text; the customer is asked to send the PO again in
  Unicode. Converting it is ADR 0010-document-intake-at-real-size-and-format decision 3, later.
- **Source anchor** (Neo nguồn): where a value was read: `sheet!cell`, or a
  page plus boxes on the rendered page, or a quote. It always carries the
  attachment's sha256. A value a model read from a PDF's text layer names its
  page and words without a box; one read from the mail itself points at the
  characters of the mail's newest part, which the quote case keeps (its
  sha256 in place of a file's).
- **Newest part** (Đoạn mới nhất của thư): the subject and what the sender
  wrote now, with quoted history and forwarded mail cut by the message's own
  structure (HTML blockquote and reply containers, `>` lines, a client's
  "On … wrote:" or "-----Original Message-----"). The only part of a body a
  model is shown.
- **Case version** (Phiên bản hồ sơ): bumped by every change. Every decision
  names the version it was made on.
- **Checker's decision** (Quyết định của người kiểm): approving or returning
  a quotation (WIV-03-023 step 9), cross-checking or returning an order
  (WIV-03-012 step 9), approving or rejecting a PO layout (ticket 30) or a
  tenant version (ticket 38). Made on a platform approval, never on a Sales
  route: the one DW1's run pauses on (`sales.quote`,
  `sales.order.cross_check`), or the run-less one a layout's or a tenant
  version's proposal opens (`sales.layout`, `sales.rules`); a maker's own
  steps are not checker's decisions (dw_sales ADR 0004).
- **DW1 run** (Lượt chạy DW1): one thing DW1 is asked to do ("DW xử lý", a
  quotation submitted, a Bravo entry recorded), on the agent runtime,
  counted against the tenant's plan.
- **Model reading** (Mô hình đọc): what a local model read from a customer's
  words, under dw_sales ADR 0005: closed-set labels and the exact text each
  came from. Code locates every text once, parses every number from its text
  and refuses a reading that leaves a word uncovered; a label is the model's
  ("Mô hình đọc, cần kiểm"), a number is DW1's ("DW1 tính từ chữ"). Stamped on
  the line's check basis with the prompt, profile and route, as `read`,
  `not_understood` (with the check that refused it) or `unavailable` (no
  usable answer: "DW1 không đọc được mô tả"). A line read this way is at best
  a candidate Sales confirms, never `exact`. Turned on per tenant by
  `sales_order_rules.model_assist` (ticket 28). Sales may instead reject a
  reading's candidates, one or several together ("Không phải mã này",
  ticket 44): the line is then `unmapped` and keeps nothing of the reading
  (no candidate, no reading, no attribute it stated), so it takes what any
  unmapped line takes, a PRV code the item master holds, typed by Sales; the
  rejection is a labelled case with nothing kept. Candidates DW1's own
  vocabulary or the convert list gave are not rejected this way, nor is a
  confirmed code: one DW applied by itself is undone ("Hoàn tác") first.
- **Message intent** (Mô hình đọc loại thư): the kind a model reads a message
  no reader accepted as (`po`, `quote_request`, `design_reply`,
  `reply_to_case`, `delivery_change`, `complaint`, `sample_request`,
  `portal_notice`, `other`), its language and the document numbers it names. Code maps the
  kind to the route and takes a number only when it is in the newest part
  and resolves to exactly one record of the sender's own customer. Stamped on
  the disposition; a readable attachment decides its message's kind first,
  and no model is asked (ticket 31).
- **Model-read request** (Yêu cầu báo giá mô hình đọc): a request for
  quotation in the mail body, a PDF's text or the customer's own sheet, read
  by a model into span text that code locates and parses. Every value it
  read is flagged `model_read` and raises `value_uncertain` on the quote
  case; Sales confirms each one, typing it as it should be, before the YCBG.
  The customer is the sender domain's; a target price the customer states
  is kept as their words only and never reaches price evidence (ticket 29).
- **Mail thread** (Luồng thư): the messages one Outlook conversation holds,
  joined by their `Message-ID`, `In-Reply-To` and `References`: each stored
  message carries a **thread key**, code's, set when it is stored (the key
  of the earliest stored message its headers name, else its own Message-ID)
  and never changed. The key is the workspace's; a thread counts for one
  customer only, applied where it is read (another customer's mail naming
  the thread joins none of its cases and shows on none). It has no status
  of its own: a thread holds the talk before a PO ("Trao đổi trước PO") and
  after it, and its cases hold the state. One thread may carry several
  cases, and one case may be talked about in several threads (dw_sales ADR
  0009). Avoid: "conversation case".
- **Outgoing message** (Thư Sales gửi): a message in a thread whose sender
  is a member's own sign-in address, as the platform's user record holds it
  (never the folder it was exported into); an upload and a mail whose
  sender the receiving system failed (SPF/DKIM/DMARC `fail`) are not. It
  never opens a case, is never routed and never changes a value, and it has
  no disposition; it tells what Sales asked and when a confirmation left. It
  shows on a case whose thread it is on when it is addressed to someone who
  wrote that case's mails there (ticket 25).
- **Reply in a case's thread** (Khách trả lời trong luồng thư): a message
  whose mail thread holds a case of the sender's own customer; it is
  attached to that case (`attached_to_case`) with no model. Where the thread
  carries several cases, the numbers the message names decide which (a
  model reads them, code resolves them), else it is routed `reply_to_case`
  with those cases offered and Sales picks one ("Chọn hồ sơ"), never
  another. Where the tenant turns it on, a model reads its **thread
  intents** and the case proposes its next step; Sales takes the step, or
  another (tickets 32, 24, 27).
- **Thread intent** (Ý định của thư): what a message in a thread does, from
  one closed set: `sends_po` (gửi PO), `requests_change` (xin điều chỉnh),
  `cancels` (huỷ), `accepts` (đồng ý), `rejects` (không đồng ý), `asks`
  (hỏi), `adds_info` (bổ sung thông tin), `sends_rfq` (gửi RFQ), `unclear`
  (chưa rõ). A message may carry several, each standing on sentences of it
  that code located; one whose sentences were not located is `unclear`. One
  table from who wrote it, the case's kind and status and an intent gives
  the step it proposes, for a person to take; Sales asking the customer
  proposes that the case waits on them (dw_sales ADR 0010, ticket 26).
- **Thread agent** (Mô hình đọc thư có tra cứu): the thread intents of a
  message read by a local model that may first look up, with read-only
  tools bound by code to the thread's one customer, the thread's earlier
  messages, its cases, a case by number, the conversion list, a lead time
  or PC's answer. Its answer is checked as the one-call reading's is; over
  its ceiling (calls, tokens, time) or with no usable answer, the one-call
  reading reads the message, else Sales, and the reading says why. Off
  until a tenant turns it on and its live eval meets the bar (dw_sales ADR
  0012, tickets 30 and 31).
- **Skill** (Kỹ năng): words that say how DW1 does one kind of work, in
  deepagents' `SKILL.md` shape: a name, a description DW1 chooses it by,
  then the instructions. The platform ships each with DW1's conduct
  (`AGENT.md`); a company may hold its own version of one, proposed by
  whoever proposes rules and approved by the head, never by its proposer.
  A skill adds no tool, scope, recipient or number. A reading stamps the
  skill versions it loaded (dw_sales ADR 0014, ticket 40).
- **DW1's agent with skills** (DW1 đọc theo kỹ năng): the thread agent
  served the skills its company holds; it loads the one that fits and is
  checked as the one-call reading is. Without a reading of its own, the
  thread agent reads the message where that is on, else the one call, else
  Sales. Off until a tenant turns it on and its live eval meets the bar
  (`skill_intents`, ticket 40).
- **Mail kind** (Loại thư của công ty): a kind of mail a company tells
  apart, named with its meaning in its mail-classifying skill (`mail-kinds`):
  the platform's version names the message intent's kinds word for word, and
  a company adds or rewords one with a skill version its head approves.
  Each kind goes on exactly one **route**, one of the message intent's kinds
  (`po`, `quote_request`, ... `other`), which code holds; a kind the
  platform does not ship carries the label Sales sees. A company's version
  naming a route code does not hold is refused when proposed. Read where a
  company turns it on (`skill_mail_kinds`) and its live eval meets the bar;
  with no kind read, the message intent's own reading classifies it
  (ticket 42).
- **Document form** (Mẫu chứng từ của khách): a customer's own request
  form, named in the company's `document-forms` skill with the customer it
  belongs to (or any) and, in words, which label or column means which
  field. A model reads a file the fixed reader does not by the sender's
  customer's forms only; code finds every value at its cell as for a
  **model-read request**, flags it for Sales, and a form opens only the
  quotation flow. A file a form reads makes the mail a quotation request,
  beside the `RFQ No.` marker. Read where a company turns it on
  (`skill_document_forms`) and its live eval meets the bar; with nothing
  read, the request is read as before (ticket 42 family 3).
- **Hand-off kind** (Loại chuyển giao của công ty): a kind of hand-off to PC
  or QA a company writes, named in its `handoffs` skill after the **mail
  kind** it is for: which fields it asks for, one of the three typed sets a
  hand-off has (`order_lines`, `lot_and_problem`, `sample_items`), the team
  it goes to (PC or QA, a team never an address) and, in words, what to
  copy. Code locates, parses and resolves every value as for the platform's
  kinds; a version naming a recipient, a send, a price, a tool, or a field
  or team code does not hold is refused when proposed. Read where a company
  turns it on (`skill_handoffs`) and its live eval meets the bar; otherwise
  the hand-off is pre-filled as before (ticket 42 family 5).
- **Reply kind** (Loại thư gửi khách của công ty): a kind of mail to a
  customer a company writes, named in its `reply-drafts` skill and worded
  as one of the platform's **AI-worded reply** drafts, which says when it is
  offered, its facts, its check and its recipients; the skill gives its
  label and how it is written. Offered beside its draft by its label. Read
  where a company turns it on (`skill_reply_drafts`) and its live eval meets
  the bar; otherwise drafts are worded as before and a company's kind is not
  offered (ticket 42 family 5).
- **AI-worded reply** (Bản AI soạn): a mail to the customer about an order
  that a local model words beside the template's draft, never in its place:
  the answer to a customer's reply read `asks` (which has no template), PC's
  answer to their change (6-DW4, 6-DW3) and the confirmation. Code gives
  every fact (never an amount) and the tenant's own letter of the kind as
  the example; a draft with a figure no fact holds, an amount, an address
  or a link is dropped and says why; the recipients are the customer's
  contacts; a person sends it. Off until a tenant turns it on and its live
  eval meets the bar (dw_sales ADR 0012, ticket 32).
- **Change request** (Yêu cầu điều chỉnh): what a customer asked to change
  on an order, in a mail's words or table: per line, the field, the value
  the case holds and the value asked, each with where the mail says it.
  Nothing of it reaches the case until the PIC confirms each line. One is
  open per case at a time; a later one waits behind it. A line changes a
  delivery date or a quantity; one asked in another unit than the line's,
  of a line the order does not have, or of a line printing several
  schedules cannot be confirmed as read and is rejected with a reason
  (ticket 27).
- **Update loop** (Vòng cập nhật): a change request on an order Sales has
  already confirmed (in Bravo), the BA's step 6: each line the PIC confirms
  joins the loop and the order does not change; once every line of the
  request is decided Sales asks PC (the **request to PC** with the values
  asked) and the order waits on PC; PC's answer is recorded per changed line;
  code compares PC's dates with the dates asked and drafts the answer to the
  customer, 6-DW4 (PC can, "Thư báo khách đáp ứng được thay đổi") or 6-DW3
  (PC proposes otherwise, "Thư báo khách phương án của PC"); Sales sends it
  and the order waits on the customer; a person records what the customer
  decided: **keep the PO** (the loop ends, the order exactly as it was),
  **ask PC again**, or **accept** (the change and PC's answer are applied, the
  first confirmed dates kept, and the order goes to `change_review`). The
  PIC then approves the exact **Bravo update file** ("Tệp cập nhật Bravo":
  the changed lines' paste-sheet rows), by its id and hash; a person enters
  it, it is cross-checked as the case's rules say by someone who made none
  of it (whoever approved the file is a maker), and its confirmation is
  sent again, which ends the loop. The loop runs on an order whose
  confirmation left, `confirmation_sent` or `confirmed` (tickets 29, 28).
- **Internal change** (Thay đổi nội bộ): Proterial's own change of a
  confirmed order, the BA's 6.1B: PC moves the dates of lines, splits them
  over several dates or cuts them (part cancelled), for overcapacity
  (`overcapacity`, Quá tải sản xuất), NG (`ng`, Hàng NG), short stock
  (`short_stock`, Thiếu hàng, vật tư) or another reason (`other`). Sales
  pastes PC's mail; a model reads the lines into the form where its step is
  on and measured (code finds every value in the paste, refuses a line the
  order does not have, leaves a value the paste does not settle to a
  person); nothing is kept until a person presses **Áp dụng**, which changes
  the order and starts its update loop at the Bravo update: the **Bravo
  update file** is the change list for Bravo's "Thay đổi chi tiết", then the
  entry, the cross-check and the confirmation again. The notice to the
  customer is a draft a person sends ("Thư báo khách thay đổi nội bộ"); it
  states no price (ticket 10). A line's deliveries never add up to more
  than the customer ordered. A **cancelled line** (PC huỷ cả dòng, W07
  "cancel all") is one PC's answer gives no delivery: it keeps what the
  customer ordered, its row in the Bravo update file holds nothing
  (quantity 0, no date), the notice says it is cancelled, the confirmation
  sent again names no date for it, and it takes no further change. Never
  every line of an order: that is the order cancelled, not changed.
- **Confirmation sent** (Đã gửi xác nhận, chờ khách): the PIC recorded the
  order's confirmation sent ("Ghi đã gửi xác nhận", with each line's
  confirmed dates), from now, or from the time of a **sent copy** on the
  case's thread that carries the processed Excel DW1 made at the case's
  version (matched by sha256), which only proposes it. Then the customer
  agrees (`confirmed`, "Khách đã đồng ý") **in words** (`accepted`, from
  their reply when recorded from one) or **by silence** (`implied`), or does
  not ("Khách từ chối": the order goes to `change_review`). A person records
  each (dw_sales ADR 0011, ticket 28).
- **Implied acceptance** (Đồng ý ngầm): a customer's silence after a
  confirmation, taken as agreement once that customer's number of days has
  passed, recorded by a person. The days, how they are counted (calendar, or
  business days Monday to Friday) and from which day (the confirmation sent,
  or the PO date) are the customer's entry in the order rules
  (`implied_acceptance`), read from the rules stamped on the case when the
  confirmation leaves. A customer with no entry never has it; the follow-up
  lane tells the PIC once the days pass (dw_sales ADR 0011).
- **Confirmed sender** (Người gửi đã xác nhận): an address no customer's
  contacts list, which Sales confirmed as one customer's, with who and on
  which mail. Bravo's contacts come first; a confirmed sender never
  overrides them (dw_sales ADR 0009).
- **Shared mail domain** (Tên miền email dùng chung): a mail domain several
  companies write from, such as the one a company and its group companies
  share, listed by the tenant in its order rules (`shared_mail_domains`,
  1.13.0). Nobody is known by it: a sender there is a customer's only by
  address (Bravo's contacts, then a confirmed sender); any other address is
  "customer not known", for a person (ticket 20). A domain several customers
  of one imported list claim is dropped from each of them on import as well.
- **Triage card** (Thẻ gợi ý): for a mail routed "other" that nothing else
  read, what DW1 thinks it is (one of the company's **mail kinds**, or none),
  the case of the sender's own customer the numbers it quotes lead to (code
  resolves them; never another customer's), and one step from the closed
  set (routed again as a delivery change, complaint, sample request, portal
  notice or reply, or attached as a reply to that case). Advice: the mail
  stays where it is until Sales takes the step, picks another or dismisses
  the card, and each decision is a labelled case. From a card, whoever
  proposes rules may teach the mail kinds a kind; the replay reads that mail
  with and without the version (`triage_card`, tickets 33 and 34, dw_sales
  ADR 0014).
- **Skill** (Kỹ năng đọc thư): an instruction in words telling DW1 how to
  read a kind of mail, for one customer or all, proposed by a PIC or the
  head and approved by the head, never its proposer. It adds no permission,
  tool, recipient or number.
- **Hand-off** (Bản chuyển PC/QA): the mail Sales sends PC or QA about a
  delivery change, a complaint or a sample request, pre-filled by code from
  a versioned template with the values a model copied and code located,
  parsed and resolved, and the customer's own sentences in quotation marks.
  Sales reviews, edits and sends it; DW1 sends nothing (ticket 33).
- **PO layout** (Mẫu PO): which label on a customer's PO form names each
  value, mapped once by a PIC on the onboarding screen and approved by
  Trưởng bộ phận Sales, who did not map it, on the platform approval the
  proposal opens (`sales.layout`). Tenant data: DW1 reads that
  customer's later POs with it, the first few with every value flagged
  `new_layout` for Sales to confirm. A model may pre-fill the mapping, label
  names only (ticket 30).

- **Follow-up** (Nhắc việc): an in-app notification DW1's `sales_followups`
  lane sends a member when a case has waited past a threshold: a PO not
  confirmed (`order_unconfirmed`: the PIC, then the head), a quote request
  waiting on Design (`quote_waiting_design`, until Design's result is read
  from Bravo's YCBG export, ticket 16), a quote due date near
  (`quote_deadline`), a case waiting on the customer (`waiting_customer`),
  an order waiting on PC's dates (`waiting_pc`, ticket 07), on Design's new
  PRV code (`waiting_design_code`, ticket 06) or on a quote opened from it
  (`waiting_quote`, ticket 09, read from the quote's own status).
  Each stage goes once per wait; outside working hours it waits for them.
  It informs and decides nothing: DW1 never mails the customer or Design.
  Every timing and switch is the tenant-overridable policy
  `sales_followups` (ticket 42); every word of it, the brief's and a
  push's is the tenant-overridable copy `sales_reminders` (ticket 42
  family 6).
- **Morning brief** (Tóm tắt buổi sáng): one notification per person each
  working morning at the policy's local time: what came in since the last
  brief and whose turn it is, what is due soon or overdue, what waits on
  whom; counts only, never an amount (ticket 42).
- **Customer reminder** (Thư nhắc khách): on a case waiting on the customer
  (`correction_requested`, `spec_discussion`), a mail DW1 drafts on request
  in the customer's language, from the PO or request number, the day the
  customer was asked and, for an order, the points asked; never an amount.
  The person opens it in their own mail program and sends it; nothing is
  sent or stored by DW1 (the contract's DW01 function 4).
- **Status assistant** (Hỏi đáp DW1): status questions on the agreed list
  (a PO's status, a quote request's status, the work waiting, the work
  overdue) answered from live data among the cases the person may see;
  anything else is said to be outside it, never guessed. The model reads
  the question and may word the answer; code finds the case and checks
  every figure; no answer carries an amount (ADR 0007).
- **Assistant session** (Phiên hỏi đáp): a person's own conversation with
  the status assistant, kept thirty days after its last turn. Its **focus**
  is the case the conversation is on, kept as the case's kind and id, so a
  follow-up such as "PO đó" means that case. Since ticket 46 a person has
  exactly two kinds: a **case conversation** (Hỏi DW1 về hồ sơ này), one per
  case, on the case's page, bound to that case and answering from it alone;
  and one **general conversation** (Trò chuyện chung), where a case named is
  a link to its own conversation. Neither is created or picked by hand.

- **Convert list** (Bảng quy đổi mã): Bravo's "Converting customer to
  PRV item" (B04), one row per direct customer and that customer's code or
  converting description (their words for the item, as their PO prints
  them), naming one PRV code. Keyed per customer: the same words name
  different items at different customers, so a line is looked up under its
  own customer only, by its code, else by its description. A row with no
  converting description, an indirect customer's, or one naming a customer
  or item not in force is refused with why (ticket 36).
- **Bravo export** (Tệp xuất từ Bravo): a master list imported as Bravo
  exports it, unedited: its header found under the title rows by shape, a
  group's label row ("3. Đã duyệt" over its SUBTOTAL) left out by shape,
  each column also known by Bravo's own label. A column Bravo does not have
  reads as unknown, or as its fail-closed default (no NOC column: not
  confirmed). An item's attributes are read from its name's spec string
  (`UL1007 1X24AWG(11/0.16) LF WHITE`); Unit Packing 0 is "not known"; a
  MOQ, pack or lead time the item master lacks is not checked, and the
  coverage says so (ticket 36).
- **Drop folder** (Thư mục thư): where real mail reaches DW without any
  access to Microsoft 365, one for DW1 and DW2 alike (2026-11-02): a DW
  account owns one OneDrive folder per person, named by the address they
  sign in with and shared with them alone; each runs a copy of one Power
  Automate flow that exports every mail reaching their Inbox as an `.eml`
  file into their folder; a PC in the plant syncs the folders and shares
  them with DW's host, read-only. The worker's `sales_mail_drop` lane reads
  each new file once (ticket 43), in the folders of the members holding
  `sales.inbox.process` only.
- **Stored mailbox** (Hộp thư DW1): the mail the lane stored, each message
  whole with its attachments' bytes, in PostgreSQL; what every screen and
  lane reads when `DW_SALES_MAILBOX=stored`. A message's id is its file's
  hash, so a copy of one file, or one mail exported from two PICs'
  mailboxes, is stored once. Every mail is stored, whoever sent it, the
  company's own included; DW1's model sorts what each one is (Đạt,
  2026-11-02). "Tên miền không đưa vào DW1" (`ignored_sender_domains`,
  1.7.0–1.8.0) is gone from 1.9.0; a version that holds it still reads.
- **Uploaded PO** (PO tải lên): a PO file a person downloaded from a
  customer's portal and uploaded on the inbox ("Tải PO lên", ticket 18),
  choosing the customer. Stored as one message of the stored mailbox whose
  sender is that person; the customer they chose, and who they are, are
  written by the server beside it, never read from the message, so a mail
  never passes for one. Read like mail (malware scan, reader sandbox,
  processing job, disposition), its customer the chosen one. The same files
  uploaded again are stored once. Needs `sales.inbox.process`. DW never logs
  into a customer's portal (Đạt, 11-13).
- **Portal export** (Tệp xuất từ cổng khách): what a customer's portal
  exports, UTF-16 tab-separated text, one PO line per row, each row naming
  its own PO number and whether it is a firm order or a **forecast** (dự
  báo). Read with that customer's layout (a PO layout of kind `csv`: which
  column holds what, which column says firm, which of its values mean firm),
  firm rows only; forecast rows are counted on the case ("N dòng dự báo,
  không đặt hàng") and never ordered. What it does not print (price,
  currency) is flagged `not_printed` (Tệp không in giá trị này, cần xác
  nhận). One export opens one case per PO number (ticket 19), each line keeping its
  own PO number. The notice mail a portal sends carries no PO: a model
  reads it as `portal_notice` and it goes to the customer's PIC.
- **Production type** (Mass / Pcs): whether a request is for mass
  production or a piece order. Bravo's SO header carries it; a pcs request
  is priced by JP & HQ, not by Sales (production ticket 05).
- **Paste sheet** (File SalesOrder): the rows Sales pastes into Bravo's
  "Đơn đặt hàng bán" grid, one row per delivery date, in the layout of the
  tenant's `sales_bravo_upload` version (2.0.0: Bravo's "Import Sales
  Order" template, rows 1–3 as it prints them). Each column reads one
  source: a value code computes from the case, a value of the customer's
  record, a fixed text, or none (left blank for the person). DW1 makes it;
  a person pastes it. Was "Bravo upload file" while the layout was a mock.
- **Customer's SalesOrder rules** (Quy tắc SalesOrder của khách,
  `sales_salesorder_rules`): per customer, the columns of the paste sheet
  that differ from the tenant's layout, each a source (a field of the
  normal reading or a value of the customer's record) and steps from a
  closed set (copy, constant, lookup, unit factor, shift days, round, cut,
  concat, multiply). A tenant rule version, learned only from a worked
  example whose replay matched, approved by the head, never the proposer;
  then applied by code to every PO of that customer (dw_sales ADR 0013).
- **Worked example** (Ví dụ mẫu): one customer's PO and the paste sheet the
  PIC made from it, with the day the PO came in, uploaded on the customer's
  row of the master data to learn its rules from.
- **Replay** (Chạy lại): the rules applied to the worked example's PO and
  compared with the PIC's file cell by cell (numbers by value, dates by
  day, text trimmed); each difference names the cell, what was expected,
  what came out and the rule. Only a replay with no difference may be sent
  for approval. A column nothing fills is left for the person who pastes,
  shown with how many rows the PIC filled, not compared.
- **SO number** (SO order): Bravo's number for a sales order, `SO` + yymm +
  sequence (`SO2611-000161`); one per customer PO as far as seen. Kept on
  the order case as `bravo_so_no`.
- **First confirmed date** (Ngày XN giao hàng đầu tiên): the delivery date
  PC confirmed first; kept when PC confirms again. **Confirmed date** (XN
  giao hàng) is the current one.
- **Sales accounting** (Sales Date / hạch toán bán hàng): the date a line is
  booked as a sale; a column of the paste sheet.
- **LME center**: the metal-price reference an order or a quotation is
  priced against (Bravo's SO header). **LME band** is the range a price
  formula reads it in (dw_sales ADR 0008).
- **Base price, BP code** (Giá cơ sở, mã BP): what Design returns with a
  YCBG reply for pricing; a price reader's field only (production ticket 11).
- **Colour code** (Mã màu): a part of a PRV code given by the item's colour,
  from the conversion workbook (production ticket 04).
- **Read-back** (Đối chiếu SO): DW1 reading the SO Bravo holds for a
  customer PO and comparing it line by line with the approved case
  (production ticket 03; the "in put PO" workbook's job).

## Roles and permission sets

| Key                    | Kind           | Vietnamese name               |
| ---------------------- | -------------- | ----------------------------- |
| `sales_pic`            | role           | Sales phụ trách (PIC)         |
| `sales_head`           | role           | Trưởng bộ phận Sales          |
| `sales_viewer`         | role           | Lãnh đạo (xem tổng hợp)       |
| `sales_price_evidence` | permission set | Xem giá đã báo cho khách khác |
| `sales_quote_approver` | permission set | Người duyệt báo giá thay      |
| `sales_export_control` | permission set | PIC kiểm soát xuất khẩu       |
| `sales_rules_editor`   | permission set | Người đề xuất quy tắc         |
| `sales_dw1`            | role           | DW1 (tài khoản dịch vụ)       |

**Rules editor** (Người đề xuất quy tắc, set `sales_rules_editor`): tenant IT
proposing a version of a Sales rule (`sales.rules.propose`, dw_sales ADR 0003
addendum of 2026-10-21). A key holding prices or price policy (the pricing
inputs, the quote rules, the order rules) also asks for `sales.price.read`, which IT never
holds, so it is not shown to IT at all. The Sales head approves; a
separation-of-duty rule keeps `platform.members.write` and
`sales.rules.approve` off one membership.

DW1 itself is the **Digital Worker** (tài khoản dịch vụ DW1). Its events
carry `actor_kind = worker`.

**DW1's service account** (Tài khoản dịch vụ DW1): one per tenant, a platform
user with a membership holding the role `sales_dw1` (`sales.inbox.process`
only), resolved by the platform like any member. It signs in nowhere. The
**mailbox lane** (DW1 tự xử lý thư, the worker's `sales_inbox` lane, ticket 16) acts under it: every new message processed in a DW1 run of its own, as if
"DW xử lý" had been pressed, except while DW1 is paused.

**Support access** (Quyền hỗ trợ, set `sales.case_support`): FPT support
staff reading a tenant's Sales cases under a grant the head issued (platform
ADR 0024, dw_sales ADR 0003 §5, ticket 22): the overview and the order and
quote lists and details, for the workspace, every amount hidden. Never a
price, never a write; no other Sales route admits it.

## Value states

How sure a value on a case is (ui-quality.md §7). Every one of them is drawn.

| State          | Label              | Meaning                                                                        |
| -------------- | ------------------ | ------------------------------------------------------------------------------ |
| `dw`           | Máy đọc            | Read by DW1 from the source anchor; not yet seen by a person                   |
| `uncertain`    | Chưa chắc chắn     | DW1 could not read it unambiguously (`value_uncertain`); blocks like a failure |
| `confirmed`    | Đã kiểm            | A person checked it against the source                                         |
| `not_opened`   | Chưa mở nguồn      | Prepared, but the preparer was never served the page or sheet it was read from |
| `hand_entered` | Sales nhập tay     | Typed by a person, who is named; the cross-checker must be someone else        |
| `superseded`   | Đã có bản thay thế | From a revision a later revision replaced                                      |

## Mapping status (customer code → PRV code)

| Status                | Label                |
| --------------------- | -------------------- |
| `exact`               | Khớp convert list    |
| `candidate`           | Một mã ứng viên      |
| `ambiguous`           | Nhiều mã ứng viên    |
| `unmapped`            | Chưa có mã           |
| `candidate_confirmed` | Sales đã xác nhận mã |

## Price evidence factors

Order history for the item (Lịch sử đặt hàng của khách), freight (Cước vận
chuyển) and management guidance (Ghi chú chỉ đạo), beside quotation history,
other customers' prices, LME and the copper component.

## Order case states

The transitions are owned by `OrderCase` and `QuoteCase` in
`dw_sales.domain`; this file is the one list of names and labels.

| State                  | Label                      |
| ---------------------- | -------------------------- |
| `received`             | Đã nhận                    |
| `checked`              | Đã kiểm tra                |
| `in_review`            | Chờ PIC tự kiểm            |
| `correction_requested` | Chờ khách sửa PO           |
| `prepared`             | PIC đã tự kiểm             |
| `uploaded_to_bravo`    | Đã nhập Bravo              |
| `cross_checked`        | Đã kiểm chéo               |
| `confirmation_sent`    | Đã gửi xác nhận, chờ khách |
| `confirmed`            | Khách đã đồng ý            |
| `change_review`        | Xem thay đổi PO            |
| `closed`               | Đã đóng                    |

Close reasons: `duplicate` (PO trùng), `not_an_order` (Không phải đơn hàng),
`superseded` (Đã có bản thay thế), `cannot_supply` (Không cung cấp được).

**Decision not applied** (Quyết định chưa được áp dụng): a cross-check
decision the platform recorded and DW1's run could not apply to the order,
because the case changed in between. The order says so until whoever
recorded its Bravo entry, or the head (`sales.order.resend_cross_check`),
raises the cross-check again (**Gửi kiểm chéo lại**, ticket 14).
Not-applied reasons: `stale_case_version` (Hồ sơ đã đổi phiên bản sau khi
quyết định), `decision_stale` (Hồ sơ không còn chờ quyết định này),
`source_not_served` (Người kiểm chưa mở nguồn của phiên bản này).

## Quote case states

| State                  | Label                    |
| ---------------------- | ------------------------ |
| `received`             | Đã nhận                  |
| `ycbg_drafted`         | Đã soạn YCBG             |
| `ycbg_recorded`        | Đã lập YCBG trên Bravo   |
| `sent_to_design`       | Chờ Design               |
| `design_replied`       | Design đã phản hồi       |
| `spec_discussion`      | Thảo luận spec với khách |
| `priced`               | Đã định giá              |
| `pending_approval`     | Chờ duyệt                |
| `returned`             | Bị trả lại định giá      |
| `approved`             | Đã duyệt                 |
| `sent`                 | Đã gửi khách             |
| `master_list_recorded` | Đã ghi master list       |
| `declined`             | Từ chối báo giá          |

Decline reasons: `not_our_product` (Không phải sản phẩm của công ty),
`design_cannot` (Design không làm được), `customer_rejected_spec` (Khách
không đồng ý spec), `commercial` (Lý do thương mại). "Quá hạn" (overdue) is
derived from the quote due date and is not a state.

## Message dispositions

| Disposition         | Label              |
| ------------------- | ------------------ |
| `case_created`      | Đã tạo hồ sơ       |
| `attached_to_case`  | Đã gắn vào hồ sơ   |
| `routed_to_sales`   | Chuyển Sales xử lý |
| `not_yet_processed` | Chưa xử lý         |

Routing reasons: `delivery_change` (Đổi lịch giao — PC, DW2), `complaint`
(Khiếu nại — QA), `design_reply_unmatched` (Phản hồi Design không khớp
YCBG), `sample_request` (Yêu cầu hàng mẫu), `customer_unknown` (Chưa xác định
được khách hàng), `attachment_unreadable` (Không đọc được file),
`attachment_locked` (Tệp có mật khẩu, DW không mở được),
`malware_detected` (Tệp đính kèm có mã độc), `reply_to_case` (Trả lời về hồ
sơ đang xử lý), `portal_notice` (PO trên cổng khách), `other` (Khác).

## Processing jobs

"DW xử lý", "DW xử lý tất cả" and DW1's mailbox lane queue a message; the
worker processes it, reading every file in the reader sandbox (ticket 25). A
message's job is in one state, beside its disposition:

| State     | Label               |
| --------- | ------------------- |
| `queued`  | Đang chờ DW1        |
| `running` | DW1 đang xử lý      |
| `done`    | DW1 đã xử lý        |
| `failed`  | DW1 chưa xử lý được |

Processing failures: `quota` (Hết lượt chạy DW1 trong ngày của gói),
`not_permitted` (Người yêu cầu không còn quyền xử lý hộp thư), `paused` (DW1
tạm dừng trước khi xử lý), `conflict` (Thư đã được xử lý trong lúc chờ),
`not_found` (Hộp thư không còn thư này), `unavailable` (Chưa quét hoặc chưa
đọc được tệp đính kèm), `model_retry` (Mô hình chưa đọc được thư, DW1 thử lại
sau), `abandoned` (Lượt xử lý bị gián đoạn), `error` (Lỗi khi xử lý).

## Finding dispositions

| Disposition          | Label                |
| -------------------- | -------------------- |
| `open`               | Chưa quyết định      |
| `accepted`           | Chấp nhận (có lý do) |
| `corrected_by_sales` | Sales sửa giá trị    |
| `ask_customer`       | Yêu cầu khách sửa    |

## Finding codes

| Code                       | Label                                |
| -------------------------- | ------------------------------------ |
| `code_unmapped`            | Mã chưa có trong convert list        |
| `code_ambiguous`           | Nhiều mã ứng viên                    |
| `price_mismatch`           | Đơn giá lệch báo giá                 |
| `currency_mismatch`        | Khác tiền tệ với báo giá             |
| `uom_mismatch`             | Khác đơn vị tính                     |
| `quotation_missing`        | Không có báo giá còn hiệu lực        |
| `lme_band_mismatch`        | Sai mức LME                          |
| `moq_violation`            | Dưới MOQ                             |
| `pack_multiple`            | Không chẵn quy cách đóng gói         |
| `reel_length_mismatch`     | Sai chiều dài mỗi cuộn               |
| `spec_mismatch`            | Sai số spec                          |
| `line_total_mismatch`      | Tổng dòng không khớp hoặc thiếu dòng |
| `value_uncertain`          | Giá trị đọc chưa chắc chắn           |
| `customer_unknown`         | Chưa xác định được khách hàng        |
| `duplicate_po`             | PO gửi trùng                         |
| `requested_date_short_lt`  | Ngày yêu cầu ngắn hơn lead time      |
| `missing_noc_esf`          | Thiếu NOC/ESF                        |
| `revised_po`               | PO sửa đổi                           |
| `revision_without_base`    | PO sửa đổi chưa thấy bản gốc         |
| `customer_temporary`       | Khách hàng mã tạm thời               |
| `sender_unverified`        | Chưa xác thực người gửi              |
| `legacy_encoding`          | Font tiếng Việt cũ (TCVN3/VNI)       |
| `requested_date_missing`   | Dòng chưa có ngày yêu cầu            |
| `files_disagree`           | Hai tệp của cùng PO ghi khác nhau    |
| `delivery_term_mismatch`   | Điều kiện giao hàng khác hồ sơ khách |
| `rfq_incomplete`           | Yêu cầu báo giá thiếu thông tin      |
| `price_below_policy_floor` | Giá dưới mức sàn                     |
| `price_floor_unknown`      | Không tính được giá sàn              |
| `price_basis_mismatch`     | Căn cứ giá đồng không đúng           |
| `above_target_price`       | Cao hơn giá khách mong muốn          |
