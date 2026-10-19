import {
  AuditOutlined,
  BuildOutlined,
  ControlOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  ScheduleOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  SolutionOutlined,
} from "@ant-design/icons";
import type { NavEntry } from "../../../lib/nav/types";
import { SALES_BADGE } from "./badge-keys";

/**
 * The Sales context's pages (DW1 Đơn hàng & Báo giá), owned here and plugged
 * into `lib/nav/registry.ts` once.
 *
 * Each item is keyed to the scope its page reads with (ticket 05): the case
 * pages to `sales.case.read`, the overview to `sales.overview.read`, the
 * rules to `sales.rules.propose` (the documents can hold price rules). So a
 * viewer who reads aggregates only (`sales_viewer`) is shown the overview and
 * nothing else, and someone with no `sales.*` scope sees no Sales group.
 * Navigation, never authorization: every route checks its scope again.
 *
 * `context` makes the group the whole bar for someone whose work is Sales
 * alone (`barNav`), and names the role prefix the Sales migration gives its
 * keys, so the shell names their Sales role from the role catalogue. The two
 * counts come from `badges.ts` beside this file.
 *
 * Nine pages do not fit one 56px row at `lg` (sales ticket 39, Đạt chose a
 * submenu): the daily pages, which carry the counts, stay on the bar, and
 * the rest sit under two submenus by the work they serve — the cases
 * ("Hồ sơ") and running the process ("Quản lý"). A count never goes inside a
 * submenu, where a closed bar would hide it. The drawer lists every page.
 */
export const salesNav: NavEntry[] = [
  {
    key: "sales",
    label: "Sales",
    icon: SolutionOutlined,
    context: { product: "Sales", roleKeyPrefix: "sales_" },
    items: [
      {
        href: "/sales",
        label: "Việc cần làm",
        hint: "Việc đang chờ bạn, cũ nhất trước, kèm tuổi và hạn (giờ Việt Nam)",
        icon: ScheduleOutlined,
        scope: "sales.case.read",
        exact: true,
        badgeKey: SALES_BADGE.myWork,
      },
      {
        href: "/sales/inbox",
        label: "Hộp thư",
        hint: "Email mẫu kèm PO và yêu cầu báo giá: hướng xử lý, lý do và người phụ trách",
        icon: InboxOutlined,
        scope: "sales.case.read",
        badgeKey: SALES_BADGE.inbox,
      },
      {
        key: "sales-cases",
        label: "Hồ sơ",
        icon: FolderOpenOutlined,
        items: [
          {
            href: "/sales/orders",
            label: "Đơn hàng",
            hint: "Đơn hàng DW1 đã đọc, kết quả kiểm tra và quyết định của Sales",
            icon: ShoppingCartOutlined,
            scope: "sales.case.read",
          },
          {
            href: "/sales/quotes",
            label: "Báo giá",
            hint: "Yêu cầu báo giá, phản hồi của Design, căn cứ giá và phê duyệt",
            icon: FileTextOutlined,
            scope: "sales.case.read",
          },
          {
            href: "/sales/review",
            label: "Kiểm chéo & duyệt",
            hint: "Đơn chờ kiểm chéo và báo giá chờ duyệt: người làm không tự kiểm",
            icon: AuditOutlined,
            scope: "sales.case.read",
          },
        ],
      },
      {
        key: "sales-manage",
        label: "Quản lý",
        icon: SettingOutlined,
        items: [
          {
            href: "/sales/layouts",
            label: "Mẫu PO",
            hint: "Mẫu PO của từng khách: Sales lập một lần, Trưởng bộ phận duyệt, DW1 đọc các PO sau theo mẫu",
            icon: BuildOutlined,
            scope: "sales.case.read",
          },
          {
            href: "/sales/rules",
            label: "Quy tắc",
            hint: "Quy tắc và nội dung của công ty: đang áp dụng bản nào, đề xuất phiên bản mới, người khác duyệt",
            icon: ControlOutlined,
            scope: "sales.rules.propose",
          },
          {
            href: "/sales/master-data",
            label: "Dữ liệu chủ",
            hint: "Khách hàng, mã hàng, bảng quy đổi mã, báo giá và LME: nhập từ tệp, xem trước, Trưởng bộ phận duyệt",
            icon: DatabaseOutlined,
            scope: "sales.case.read",
          },
          {
            href: "/sales/overview",
            label: "Tổng quan quy trình",
            hint: "Số hồ sơ ở mỗi bước WIV-03-012 và WIV-03-023, trên bộ mẫu giả lập",
            icon: DashboardOutlined,
            scope: "sales.overview.read",
          },
        ],
      },
    ],
  },
];
