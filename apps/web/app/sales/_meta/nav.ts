import {
  AuditOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  InboxOutlined,
  ScheduleOutlined,
  ShoppingCartOutlined,
  SolutionOutlined,
} from "@ant-design/icons";
import type { NavEntry } from "../../../lib/nav/types";

/**
 * The Sales context's pages (DW1 Đơn hàng & Báo giá), owned here and plugged
 * into `lib/nav/registry.ts` once.
 *
 * Each item is keyed to the scope its page reads with (ticket 05): the case
 * pages to `sales.case.read`, the overview to `sales.overview.read`. So a
 * viewer who reads aggregates only (`sales_viewer`) is shown the overview and
 * nothing else, and someone with no `sales.*` scope sees no Sales group.
 * Navigation, never authorization: every route checks its scope again.
 */
export const salesNav: NavEntry[] = [
  {
    key: "sales",
    label: "Sales",
    icon: SolutionOutlined,
    items: [
      {
        href: "/sales",
        label: "Việc cần làm",
        hint: "Việc đang chờ bạn, cũ nhất trước, kèm tuổi và hạn (giờ Việt Nam)",
        icon: ScheduleOutlined,
        scope: "sales.case.read",
        exact: true,
      },
      {
        href: "/sales/inbox",
        label: "Hộp thư",
        hint: "Email mẫu kèm PO và yêu cầu báo giá: hướng xử lý, lý do và người phụ trách",
        icon: InboxOutlined,
        scope: "sales.case.read",
      },
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
      {
        href: "/sales/master-data",
        label: "Dữ liệu giả lập",
        hint: "Khách hàng, mã hàng, bảng quy đổi mã, báo giá và LME của bản demo (chỉ đọc)",
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
];
