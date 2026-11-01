import {
  ControlOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  PlusCircleOutlined,
  ScheduleOutlined,
  ShoppingOutlined,
} from "@ant-design/icons";
import type { NavEntry } from "../../../lib/nav/types";
import { SCOPE } from "../_lib/scopes";

/**
 * The Purchasing context's pages (DW2 Mua hàng), owned here and plugged into
 * `lib/nav/registry.ts` once. Each item is keyed to the scope its page reads
 * with: the cases and the mailbox to `purchasing.request.read`, a
 * requester's own pages to `purchasing.request.create` or `.read_own`, the
 * settings to `purchasing.rules.propose`. Navigation, never authorization:
 * every route checks its scope again.
 */
export const purchasingNav: NavEntry[] = [
  {
    key: "purchasing",
    label: "Mua hàng",
    icon: ShoppingOutlined,
    context: { product: "DW2 Mua hàng", roleKeyPrefix: "purchasing_" },
    items: [
      {
        href: "/purchasing",
        label: "Việc của tôi",
        hint: "Việc DW2 đang chờ bạn: duyệt, xem lại yêu cầu máy đọc, hỏi giá, soạn PO",
        icon: ScheduleOutlined,
        exact: true,
        // A director who approves the last tier holds that scope and no other.
        anyScope: [SCOPE.read, SCOPE.readOwn, SCOPE.approveLast],
      },
      {
        href: "/purchasing/new",
        label: "Tôi cần mua…",
        hint: "Viết điều bạn cần bằng lời; DW2 soạn yêu cầu mua hàng để bạn xem rồi gửi",
        icon: PlusCircleOutlined,
        scope: SCOPE.create,
      },
      {
        href: "/purchasing/inbox",
        label: "Hộp thư",
        hint: "Thư đến hộp thư mua hàng: DW2 đã mở hồ sơ nào, thư nào cần người xem và vì sao",
        icon: InboxOutlined,
        scope: SCOPE.read,
      },
      {
        href: "/purchasing/requests",
        label: "Hồ sơ mua hàng",
        hint: "Mọi yêu cầu mua hàng theo trạng thái, mới nhất trước",
        icon: FolderOpenOutlined,
        anyScope: [SCOPE.read, SCOPE.readOwn],
      },
      {
        href: "/purchasing/settings",
        label: "Cài đặt DW2",
        hint: "Công tắc tự động của từng bước và quy tắc mua hàng: đổi bằng lời, người khác duyệt",
        icon: ControlOutlined,
        scope: SCOPE.propose,
      },
    ],
  },
];
