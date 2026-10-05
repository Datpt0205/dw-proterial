"use client";

import { CheckOutlined, DownOutlined } from "@ant-design/icons";
import { Button, Dropdown, theme, Typography } from "antd";
import { useAuth } from "../lib/auth/auth-context";

/**
 * The active workspace and its company, beside the brand (the prototype's
 * workspace block: a small "Workspace" line, the workspace, the company).
 * With more than one membership it opens a menu to switch (the auth context
 * re-activates the chosen membership); with one it only shows. Nothing
 * renders for an operator with no workspace.
 */
export function WorkspaceSwitcher() {
  const { active, memberships, selectWorkspace } = useAuth();
  const { token } = theme.useToken();
  if (!active) return null;
  const multiple = memberships.length > 1;

  const block = (
    <span className="flex min-w-0 flex-col items-start leading-tight">
      <Typography.Text
        type="secondary"
        className="uppercase leading-tight"
        style={{ fontSize: token.fontSizeSM }}
      >
        Workspace
      </Typography.Text>
      <Typography.Text
        strong
        ellipsis
        className="max-w-48 leading-tight"
        style={{ fontSize: token.fontSizeSM + 1 }}
      >
        {active.workspaceName}
      </Typography.Text>
      <Typography.Text
        type="secondary"
        ellipsis
        className="max-w-48 leading-tight"
        style={{ fontSize: token.fontSizeSM }}
      >
        {active.tenantName}
      </Typography.Text>
    </span>
  );

  if (!multiple)
    return (
      <div
        className="flex min-w-0 items-center px-2"
        title={`${active.tenantName} · ${active.workspaceName}`}
      >
        {block}
      </div>
    );

  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        selectedKeys: [active.workspaceId],
        items: memberships.map((m) => ({
          key: m.workspaceId,
          label: `${m.workspaceName} · ${m.tenantName}`,
          extra:
            m.workspaceId === active.workspaceId ? (
              <CheckOutlined aria-hidden />
            ) : null,
        })),
        onClick: ({ key }) => selectWorkspace(key),
      }}
    >
      <Button
        type="text"
        className="h-auto py-1"
        aria-label={`Workspace: ${active.workspaceName}, ${active.tenantName}. Chọn workspace khác`}
      >
        <span className="flex items-center gap-2">
          {block}
          <DownOutlined aria-hidden />
        </span>
      </Button>
    </Dropdown>
  );
}
