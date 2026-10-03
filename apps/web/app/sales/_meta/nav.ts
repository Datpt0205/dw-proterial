import {
  BriefcaseBusiness,
  ClipboardList,
  Database,
  FileText,
  Inbox,
  Workflow,
} from "lucide-react";
import type { NavEntry } from "../../../lib/nav/types";

/**
 * The Sales context's pages (DW1 Đơn hàng & Báo giá), owned here and plugged
 * into `lib/nav/registry.ts` once. `sales.read` is the scope the context's API
 * checks on these reads (ticket 05); until it is seeded only a role that holds
 * every scope sees the group.
 */
export const salesNav: NavEntry[] = [
  {
    key: "sales",
    label: "Sales",
    icon: BriefcaseBusiness,
    items: [
      {
        href: "/sales",
        label: "Tổng quan quy trình",
        hint: "Các bước WIV-03-012 và WIV-03-023, và số hồ sơ đang ở mỗi bước",
        icon: Workflow,
        scope: "sales.read",
        exact: true,
      },
      {
        href: "/sales/inbox",
        label: "Hộp thư",
        hint: "Email mẫu kèm PO và yêu cầu báo giá, nơi DW bắt đầu xử lý",
        icon: Inbox,
        scope: "sales.read",
      },
      {
        href: "/sales/orders",
        label: "Đơn hàng",
        hint: "Đơn hàng DW đã đọc, kết quả kiểm tra và quyết định của Sales",
        icon: ClipboardList,
        scope: "sales.read",
      },
      {
        href: "/sales/quotes",
        label: "Báo giá",
        hint: "Yêu cầu báo giá, phản hồi của Design, căn cứ giá và phê duyệt",
        icon: FileText,
        scope: "sales.read",
      },
      {
        href: "/sales/master-data",
        label: "Dữ liệu giả lập",
        hint: "Khách hàng, mã hàng, bảng quy đổi mã, báo giá và LME của bản demo (chỉ đọc)",
        icon: Database,
        scope: "sales.read",
      },
    ],
  },
];
