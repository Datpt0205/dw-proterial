"use client";

import { CheckOutlined, DownOutlined, RobotOutlined } from "@ant-design/icons";
import { Avatar, Button, Dropdown, theme, Typography } from "antd";
import { navPages } from "../lib/nav/visibility";
import type { NavGroup } from "../lib/nav/types";

/** The logo and the product the bar is: "Digital Worker · DW1 …". */
export function BrandMark({ product }: { product?: string }) {
  const { token } = theme.useToken();
  return (
    <span className="flex items-center gap-2">
      <Avatar
        shape="square"
        size={28}
        icon={<RobotOutlined />}
        style={{
          backgroundColor: token.colorPrimary,
          borderRadius: token.borderRadius,
        }}
      />
      <Typography.Text
        strong
        className="hidden whitespace-nowrap sm:inline"
        style={{ fontSize: token.fontSizeLG }}
      >
        Digital Worker
        {product ? (
          <Typography.Text
            type="secondary"
            style={{ fontSize: token.fontSizeLG }}
          >
            {` · ${product}`}
          </Typography.Text>
        ) : null}
      </Typography.Text>
    </span>
  );
}

/**
 * Several Digital Workers for one person (DW1 Đơn hàng & Báo giá, DW2 Mua
 * hàng): the brand opens a menu of them, the one in use ticked, and picking
 * one opens its first page (Đạt, 2026-10-28: "đổi thành chỗ swap DW2 ... để
 * khỏi nhầm lẫn"). Someone who works in one sees the plain brand instead.
 */
export function ContextSwitcher({
  contexts,
  active,
  onPick,
}: {
  contexts: readonly NavGroup[];
  active: NavGroup | null;
  onPick: (href: string) => void;
}) {
  const product = active?.context?.product;
  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        selectedKeys: active ? [active.key] : [],
        items: contexts.map((group) => ({
          key: group.key,
          label: group.context!.product,
          extra:
            group.key === active?.key ? <CheckOutlined aria-hidden /> : null,
        })),
        onClick: ({ key }) => {
          const first = navPages(contexts.filter((g) => g.key === key))[0];
          if (first) onPick(first.href);
        },
      }}
    >
      <Button
        type="text"
        className="h-auto px-1 py-1"
        aria-label={`Đang dùng ${product ?? "Digital Worker"}. Chọn Digital Worker khác`}
      >
        <span className="flex items-center gap-2">
          <BrandMark product={product} />
          <DownOutlined aria-hidden />
        </span>
      </Button>
    </Dropdown>
  );
}
