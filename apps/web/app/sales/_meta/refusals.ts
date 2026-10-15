/**
 * Sales refusals in Vietnamese, by the code the API names them with
 * (`details.rule`, else `details.reason`), plugged into `errorMessage()` in
 * `lib/error-message.ts` once.
 *
 * Only the refusals whose sentence the server still writes in English are
 * here. Where dw_sales already words a refusal in Vietnamese
 * (`decision_stale`, `template_version_gone`, `worker_paused`,
 * `source_not_served`, the `template_*` and drafting reasons, ...), the
 * server's sentence is shown as it is: a second wording here would be a
 * second owner of it. A refusal that names no code falls back to the server's
 * sentence too.
 */
export const SALES_REFUSALS: Readonly<Record<string, string>> = {
  // Separation of duties: the order's cross-check, a rule version, the
  // stored constraint (dw_sales `_rows._RULES`); a layout's proposer too.
  maker_checker:
    "Tách nhiệm: người đã làm hoặc đề xuất việc này không tự kiểm, tự duyệt được.",
  approver_not_pricer:
    "Tách nhiệm: người định giá báo giá này không tự duyệt được.",
  stale_case_version:
    "Hồ sơ đã thay đổi từ khi bạn mở: tải lại để xem phiên bản mới.",
  layout_decided: "Mẫu PO vừa được quyết định: tải lại để xem kết quả.",
  message_already_processed: "Thư này đã được xử lý vào một hồ sơ.",
  assignee_not_eligible:
    "Người được chọn không làm loại hồ sơ này ở workspace này: chọn người khác.",
  case_closed: "Hồ sơ đã đóng nên không giao lại được.",
  platform_version_reused:
    "Số phiên bản này trùng với một phiên bản nền tảng phát hành: đặt số khác cho phiên bản của công ty.",
  rules_version_gone:
    "Hồ sơ được mở theo một phiên bản quy tắc báo giá không còn nữa, nên bước này chưa làm được.",
  printed_schedules:
    "Dòng này có nhiều lịch giao in trên PO: ngày giao phải hỏi khách, không sửa tay được.",
  date_per_schedule: "Mỗi lịch giao của một dòng cần đúng một ngày xác nhận.",
  resend_cross_check:
    "Chỉ người đã ghi Bravo hoặc Trưởng bộ phận gửi lại kiểm chéo được.",
};
