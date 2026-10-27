/**
 * How a scope (a permission) reads to a person: the ONE label table for scopes
 * in the web app (the admin page, the role catalog, separation of duties, a
 * refusal that names the permission it lacks). The role catalog and the code
 * own the scopes; this owns only the wording, and `__tests__/scopes.test.ts`
 * fails when the platform seeds a scope, or Sales declares one, that this
 * table does not name. An unnamed scope shows as its code, never as nothing.
 *
 * PLUG-IN POINT: a bounded context adds its own scopes' labels here, in the
 * same change that declares them.
 */
const SCOPE_LABELS: Record<string, string> = {
  "approvals.read": "Xem yêu cầu duyệt",
  "approvals.pending": "Xem yêu cầu chờ duyệt",
  "approvals.decide": "Quyết yêu cầu duyệt",
  "audit.events": "Xem nhật ký hệ thống",
  "directory.read": "Xem danh bạ thành viên",
  "feedback.inbox": "Đọc góp ý",
  "integrations.read": "Xem kết nối",
  "knowledge.read": "Đọc tri thức",
  "knowledge.write": "Thêm và sửa tri thức",
  "memory.read": "Xem bộ nhớ",
  "memory.review": "Duyệt bộ nhớ",
  "runs.read": "Xem lượt chạy",
  "platform.admin": "Toàn quyền quản trị",
  "platform.members.read": "Xem thành viên",
  "platform.members.write": "Quản lý thành viên",
  "platform.roles.read": "Xem danh mục vai",
  "platform.usage.read": "Xem mức sử dụng",
  "platform.sod_waivers.write": "Miễn trừ tách nhiệm",
  "platform.tenant.settings.write": "Sửa cài đặt công ty",
  "platform.workspaces.write": "Quản lý không gian làm việc",
  "support.grant": "Cấp quyền hỗ trợ",
  "support.request": "Yêu cầu hỗ trợ",
  // Sales (dw_sales.application.access.SalesScopes).
  "sales.overview.read": "Xem tổng quan quy trình",
  "sales.case.read": "Xem hồ sơ Sales",
  "sales.case.assign": "Giao hồ sơ",
  "sales.price.read": "Xem giá",
  "sales.price.other_customers.read": "Xem giá của khách khác",
  "sales.inbox.process": "Cho DW1 xử lý thư",
  "sales.order.prepare": "Làm đơn hàng",
  "sales.order.cross_check": "Kiểm chéo đơn hàng",
  "sales.order.resend_cross_check": "Gửi kiểm chéo lại",
  "sales.quote.prepare": "Làm báo giá",
  "sales.quote.approve": "Duyệt báo giá",
  "sales.compliance.ack": "Xác nhận kiểm soát xuất khẩu",
  "sales.worker.pause": "Tạm dừng DW1",
  "sales.worker.resume": "Chạy lại DW1",
  "sales.layout.approve": "Duyệt mẫu PO",
  "sales.rules.propose": "Đề xuất quy tắc",
  "sales.rules.approve": "Duyệt quy tắc",
  "sales.master_data.import": "Nhập dữ liệu chủ",
  "sales.master_data.approve": "Duyệt dữ liệu chủ",
};

/** Label for a scope; one this table does not name shows as its code. */
export function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}
