"use client";

import Link from "next/link";
import { LogoutOutlined, ProfileOutlined } from "@ant-design/icons";
import { Avatar, Button, Dropdown, theme, Typography } from "antd";
import { useAuth } from "../lib/auth/auth-context";
import { initials } from "../lib/initials";
import { NAV_ITEMS } from "../lib/nav/registry";
import { displayRole } from "../lib/nav/roles";

// The menu's second door to the audit trail reads its scope from the nav
// registry's entry, the one owner of "who is offered /audit": hard-coding a
// scope here kept offering every member a page the API refuses
// (approval-audit-and-workspace/02).
const AUDIT_LOG = NAV_ITEMS.find((item) => item.href === "/audit");

/**
 * The account at the end of the navbar: initials, and on a wide screen the
 * name and the role the person works as; the menu repeats them with the
 * email, the activity log where the person may read it, and sign-out. The
 * role comes from `displayRole`, which names a context's role from the role
 * catalogue.
 */
export function SessionChip({
  contextPrefix = null,
}: {
  /** The role prefix of the context the bar is, when it is one. */
  contextPrefix?: string | null;
}) {
  const {
    status,
    displayName,
    email,
    roles,
    active,
    isPlatformOperator,
    logout,
    hasScope,
  } = useAuth();
  const { token } = theme.useToken();
  if (status !== "ready") return null;

  const role = displayRole({
    roles,
    roleNames: active?.roleNames ?? {},
    contextPrefix,
    isPlatformOperator,
  });
  const name = displayName || "Người dùng";

  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      popupRender={(menu) => (
        <div
          className="w-72 max-w-[90vw] overflow-hidden"
          style={{
            background: token.colorBgElevated,
            borderRadius: token.borderRadiusLG,
            boxShadow: token.boxShadowSecondary,
          }}
        >
          <div className="flex flex-col gap-0.5 px-4 pb-2 pt-3">
            <Typography.Text strong>{name}</Typography.Text>
            {email ? (
              <Typography.Text type="secondary">{email}</Typography.Text>
            ) : null}
            {role ? <Typography.Text>{role}</Typography.Text> : null}
          </div>
          {menu}
        </div>
      )}
      menu={{
        items: [
          ...(AUDIT_LOG && (!AUDIT_LOG.scope || hasScope(AUDIT_LOG.scope))
            ? [
                {
                  key: "audit",
                  icon: <ProfileOutlined aria-hidden />,
                  label: <Link href="/audit">Nhật ký hoạt động</Link>,
                },
              ]
            : []),
          {
            key: "logout",
            icon: <LogoutOutlined aria-hidden />,
            label: "Đăng xuất",
            onClick: logout,
          },
        ],
      }}
    >
      <Button
        type="text"
        className="h-auto px-1 py-1"
        aria-label={`Tài khoản: ${name}${role ? `, ${role}` : ""}`}
      >
        <span className="flex items-center gap-2">
          <Avatar
            size={32}
            style={{
              backgroundColor: token.colorFill,
              color: token.colorText,
              fontSize: token.fontSizeSM,
              fontWeight: token.fontWeightStrong,
            }}
          >
            {initials(name)}
          </Avatar>
          <span className="hidden min-w-0 flex-col items-start leading-tight 2xl:flex">
            <Typography.Text
              strong
              ellipsis
              className="max-w-44 leading-tight"
              style={{ fontSize: token.fontSizeSM + 1 }}
            >
              {name}
            </Typography.Text>
            {role ? (
              <Typography.Text
                type="secondary"
                ellipsis
                className="max-w-44 leading-tight"
                style={{ fontSize: token.fontSizeSM }}
              >
                {role}
              </Typography.Text>
            ) : null}
          </span>
        </span>
      </Button>
    </Dropdown>
  );
}
