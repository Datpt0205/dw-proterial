import type { SalesSchemas } from "@dw/api-client";

export type Mapping = SalesSchemas["LayoutMapping"];
export type MappingField = Exclude<
  keyof Mapping,
  | "kind"
  | "thousands_separator"
  | "decimal_separator"
  | "date_format"
  | "pdf_columns"
>;

/**
 * The fields a person maps on a PO form, in the order the screen asks for
 * them, each with its words (ticket 30). The owner of which fields exist and
 * which are optional is `LayoutMapping` in `dw_sales.domain.layouts`; the
 * server refuses a mapping that leaves a required one out.
 */
export const LAYOUT_FIELDS: readonly {
  field: MappingField;
  label: string;
  optional?: boolean;
  pdf?: false;
}[] = [
  { field: "po_no", label: "Số PO" },
  { field: "revision", label: "Lần sửa đổi", optional: true },
  { field: "po_date", label: "Ngày PO" },
  { field: "currency", label: "Tiền tệ" },
  { field: "line_no", label: "Cột số dòng" },
  { field: "customer_item_code", label: "Cột mã hàng của khách" },
  { field: "description", label: "Cột mô tả" },
  { field: "quantity", label: "Cột số lượng" },
  { field: "uom", label: "Cột đơn vị tính" },
  { field: "unit_price", label: "Cột đơn giá" },
  { field: "amount", label: "Cột thành tiền" },
  { field: "requested_date", label: "Cột ngày giao yêu cầu" },
  { field: "total_label", label: "Nhãn tổng cộng" },
  {
    field: "page_label",
    label: "Nhãn số trang (mẫu mỗi trang một sheet)",
    optional: true,
    pdf: false,
  },
];

/** Why a mapping is refused, by the check's code (`LayoutProblem`). */
export const LAYOUT_PROBLEM: Record<string, string> = {
  label_not_found: "không thấy nhãn này trên mẫu",
  label_repeated: "nhãn này có hơn một lần trên mẫu",
  columns_not_on_one_row: "các tiêu đề cột không nằm trên cùng một hàng",
  unreadable: "không đọc được mẫu với cách gán này",
  no_total: "mẫu không có dòng tổng cộng: không lập được mẫu",
  line_total_mismatch: "tổng các dòng không khớp tổng in trên mẫu",
  quantity_not_whole:
    "số lượng đọc ra không phải số nguyên: có thể đã gán nhầm với đơn giá",
  price_out_of_quoted_range:
    "đơn giá ngoài khoảng báo giá của khách: có thể đã gán nhầm với số lượng",
  requested_before_po_date: "ngày giao đọc ra trước ngày PO",
  requested_is_po_date:
    "ngày giao trùng ngày PO ở mọi dòng: có thể là ngày đặt hàng",
  no_item_known:
    "không mã hàng nào đọc ra có trong bảng quy đổi hay danh mục: kiểm tra cột mã hàng",
  incomplete_proposal: "mô hình gợi ý thiếu nhãn bắt buộc",
};

export const LAYOUT_STATUS: Record<string, string> = {
  proposed: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
  superseded: "Đã thay bằng mẫu mới",
};

/** A refused check as a sentence: the field's words, then why. */
export function problemText(problem: string): string {
  const [code, field] = problem.split(":");
  const named = LAYOUT_FIELDS.find((f) => f.field === field)?.label;
  const why = LAYOUT_PROBLEM[code ?? ""] ?? code ?? problem;
  return named
    ? `${named}: ${why}`
    : why.charAt(0).toUpperCase() + why.slice(1);
}
