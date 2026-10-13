"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Table, Tag, Tooltip, Typography, theme } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import type { MySupportGrant } from "@dw/api-client";
import { PageHeader, RegionState } from "@dw/ui";
import { LoadError } from "../../components/load-error";
import { useAuth } from "../../lib/auth/auth-context";
import {
  formatDateTime,
  formatDuration,
  instantMs,
  TIME_ZONE_LABEL,
} from "../../lib/dates";
import { useCachedResource } from "../../lib/use-cached-resource";
import { useNow } from "../../lib/use-now";
import { apiClient } from "../../lib/session";
import { supportLanding } from "../../lib/support/registry";
import {
  clearSupportMfaRequired,
  startSupportGrant,
  supportMfaRequired,
} from "../../lib/support/session";

const ENDED_REASON = "Quyền đã hết hạn hoặc bị thu hồi.";
// Under this many hours left, the time left is drawn as a warning.
const SOON_MS = 4 * 3_600_000;

/** What a grant's state reads as; anything not `active` cannot be opened. */
const STATE_LABEL: Record<string, string> = {
  active: "Đang hiệu lực",
  expired: "Đã hết hạn",
  revoked: "Khách đã thu hồi",
  ineffective: "Mất hiệu lực",
};

/**
 * "Quyền hỗ trợ của tôi" (support-access ticket 03): the grants a customer
 * gave and the support team assigned to the viewer, with each one's scope,
 * mode and end, in giờ Việt Nam. "Mở" opens one: every later request carries
 * it (`lib/session.ts`) until "Thoát quyền hỗ trợ" or the grant ends. The
 * server decides everything again on every request.
 */
export default function SupportPage() {
  const { isSupportStaff, logout } = useAuth();
  const [mfa, setMfa] = useState(false);
  useEffect(() => setMfa(supportMfaRequired()), []);

  if (!isSupportStaff) {
    return (
      <RegionState
        kind="forbidden"
        title="Chỉ dành cho nhân viên hỗ trợ"
        description="Trang này liệt kê quyền hỗ trợ khách cấp cho nhân viên hỗ trợ."
      />
    );
  }
  if (mfa) {
    return (
      <RegionState
        kind="forbidden"
        title="Cần xác thực hai lớp để dùng quyền hỗ trợ"
        description="Phiên đăng nhập này chưa có yếu tố thứ hai. Hãy đăng xuất rồi đăng nhập lại với mã xác thực hai lớp."
        action={
          <Button
            icon={<LogoutOutlined aria-hidden />}
            onClick={() => {
              clearSupportMfaRequired();
              logout();
            }}
          >
            Đăng xuất để đăng nhập lại
          </Button>
        }
      />
    );
  }
  return <MyGrants />;
}

function MyGrants() {
  const router = useRouter();
  const now = useNow();
  const { token } = theme.useToken();
  const grants = useCachedResource<MySupportGrant[]>(
    "support/my-grants",
    useCallback(() => apiClient().listMySupportGrants(), []),
  );

  const open = (grant: MySupportGrant) => {
    startSupportGrant({
      id: grant.id,
      code: grant.code,
      tenantId: grant.tenant_id,
      workspaceId: grant.workspace_id,
      resourceType: grant.resource_type,
      resourceId: grant.resource_id,
      scopeSetKey: grant.scope_set_key,
      scopes: grant.scopes,
      expiresAt: grant.expires_at,
    });
    router.push(
      supportLanding(
        grant.resource_type,
        grant.scope_set_key,
        grant.resource_id,
      ),
    );
  };

  const left = (grant: MySupportGrant) => {
    if (grant.state === "revoked")
      return <Typography.Text type="danger">Khách đã thu hồi</Typography.Text>;
    const end = instantMs(grant.expires_at);
    if (grant.state === "expired" || (end !== null && end <= now))
      return <Typography.Text type="danger">Đã hết hạn</Typography.Text>;
    if (end === null) return null;
    const remaining = end - now;
    return (
      <Typography.Text
        style={
          remaining < SOON_MS ? { color: token.colorWarningText } : undefined
        }
      >
        {`còn ${formatDuration(remaining)}`}
      </Typography.Text>
    );
  };

  return (
    <>
      <PageHeader
        title="Quyền hỗ trợ của tôi"
        subtitle="Dữ liệu của khách chỉ mở được qua quyền hỗ trợ do khách cấp. Mỗi quyền có phạm vi, chế độ và hạn; mọi thao tác ghi nhật ký với mã quyền."
      />
      {grants.error ? (
        <LoadError error={grants.error} onRetry={grants.reload} />
      ) : (
        <Table<MySupportGrant>
          rowKey="id"
          loading={grants.loading}
          dataSource={grants.data ?? []}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: grants.loading ? (
              " "
            ) : (
              <RegionState
                kind="empty"
                title="Chưa có quyền hỗ trợ nào"
                description="Khi khách cấp quyền, quyền hiện ở đây kèm phạm vi và hạn."
                compact
              />
            ),
          }}
          columns={[
            {
              title: "Khách",
              key: "tenant",
              render: (_, grant) => (
                <>
                  <Typography.Text strong>{grant.tenant_name}</Typography.Text>
                  <br />
                  <Typography.Text code>{grant.code}</Typography.Text>
                </>
              ),
            },
            {
              title: "Workspace",
              dataIndex: "workspace_name",
              responsive: ["lg"],
            },
            {
              title: "Phạm vi · chế độ",
              key: "scope",
              responsive: ["lg"],
              render: (_, grant) =>
                `${grant.resource_label} · ${grant.scope_set_label}`,
            },
            {
              title: `Hết hạn (${TIME_ZONE_LABEL})`,
              key: "expires",
              render: (_, grant) => (
                <>
                  {formatDateTime(grant.expires_at, { zoneLabel: false })}
                  <br />
                  {left(grant)}
                </>
              ),
            },
            {
              title: "Trạng thái",
              key: "state",
              render: (_, grant) => (
                <Tag color={grant.state === "active" ? "success" : "error"}>
                  {STATE_LABEL[grant.state] ?? grant.state}
                </Tag>
              ),
            },
            {
              title: "",
              key: "open",
              fixed: "right",
              render: (_, grant) => {
                const ended =
                  grant.state !== "active" ||
                  (instantMs(grant.expires_at) ?? Infinity) <= now;
                const button = (
                  <Button
                    type="primary"
                    disabled={ended}
                    onClick={() => open(grant)}
                    aria-label={`Mở quyền ${grant.code}`}
                  >
                    Mở
                  </Button>
                );
                return ended ? (
                  <Tooltip title={ENDED_REASON}>
                    <span>{button}</span>
                  </Tooltip>
                ) : (
                  button
                );
              },
            },
          ]}
        />
      )}
    </>
  );
}
