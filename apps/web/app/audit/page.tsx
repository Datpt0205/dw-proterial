"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Button,
  Card,
  Flex,
  Input,
  Skeleton,
  Table,
  Tag,
  Typography,
} from "antd";
import { AuditOutlined, ReloadOutlined } from "@ant-design/icons";
import type { AuditEvent } from "@dw/contracts";
import { PageHeader, RegionState } from "@dw/ui";
import { LoadError } from "../../components/load-error";
import { LoadMore } from "../../components/load-more";
import { formatDateTime } from "../../lib/dates";
import { apiClient } from "../../lib/session";
import { useCachedPages } from "../../lib/use-cached-pages";

const ACTIONS: Record<string, { label: string; color: string }> = {
  "run.started": { label: "Bắt đầu lượt chạy", color: "processing" },
  "run.waiting_approval": { label: "Chờ duyệt", color: "warning" },
  "run.resumed": { label: "Chạy tiếp", color: "processing" },
  "run.completed": { label: "Xong lượt chạy", color: "success" },
  "approval.decided": { label: "Đã quyết yêu cầu", color: "success" },
  "tool.executed": { label: "Đã chạy công cụ", color: "default" },
  // PLUG-IN POINT: a bounded context adds its own actions here. An unmapped
  // action still shows, as "Hoạt động hệ thống" — a row is never dropped.
};
const OTHER_ACTION = { label: "Hoạt động hệ thống", color: "default" };

/** The key a support grant's events carry their grant under (ADR 0024). */
const GRANT_DETAIL = "support_grant_id";

function detailText(event: AuditEvent, key: string): string | null {
  const value = event.details[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Who did it, as the server names them today; an actor that is no user
 * (a background lane) has no name and shows its short id. */
function actorName(event: AuditEvent): string {
  return event.actor_display_name ?? `${event.actor_id.slice(0, 8)}…`;
}

function grantHref(grantId: string): string {
  return `/audit?${GRANT_DETAIL}=${encodeURIComponent(grantId)}`;
}

export default function AuditPage() {
  // `useSearchParams` needs a Suspense boundary above the component calling it.
  return (
    <Suspense fallback={<Skeleton active paragraph={{ rows: 6 }} />}>
      <AuditTrail />
    </Suspense>
  );
}

function AuditTrail() {
  // One grant's trail has its own URL, so it can be sent to a colleague.
  const grantId = useSearchParams().get(GRANT_DETAIL);
  const [filter, setFilter] = useState("");

  const { items, loading, loadingMore, error, hasMore, loadMore, reload } =
    useCachedPages(
      `audit:events:${grantId ?? "all"}`,
      useCallback(
        (cursor: string | null) =>
          apiClient().listAuditEvents({
            cursor,
            supportGrantId: grantId ?? undefined,
          }),
        [grantId],
      ),
    );

  const visible = items.filter(
    (event) =>
      !filter ||
      event.action.includes(filter) ||
      event.resource_type.includes(filter) ||
      event.resource_id.includes(filter) ||
      actorName(event).toLowerCase().includes(filter.toLowerCase()),
  );
  // The grant's own code, as the customer knows it, once a row has shown it.
  const grantCode =
    grantId == null
      ? null
      : (items.map((event) => detailText(event, "code")).find(Boolean) ??
        `${grantId.slice(0, 8)}…`);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        icon={<AuditOutlined />}
        title="Nhật ký kiểm toán"
        subtitle="Lịch sử được ghi liên tục và không ai sửa được, kể cả quản trị viên."
        actions={
          <>
            <Input.Search
              allowClear
              className="w-56"
              aria-label="Tìm trong nhật ký"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Tìm thao tác hoặc bản ghi…"
            />
            <Button
              icon={<ReloadOutlined aria-hidden />}
              aria-label="Tải lại"
              onClick={reload}
            />
          </>
        }
      />
      <Flex vertical gap="middle">
        {grantCode != null && (
          <Flex wrap gap="small" align="center">
            <Typography.Text>Đang lọc:</Typography.Text>
            <Tag>Quyền hỗ trợ {grantCode}</Tag>
            <Link href="/audit">Xóa bộ lọc</Link>
          </Flex>
        )}
        {error != null && <LoadError error={error} onRetry={reload} />}
        {loading && error == null && <RegionState kind="loading" />}
        {!loading && error == null && visible.length === 0 && (
          <RegionState
            kind="empty"
            title={
              grantCode != null
                ? `Quyền hỗ trợ ${grantCode} chưa có sự kiện nào khớp`
                : "Không có sự kiện nào khớp"
            }
          />
        )}
        {visible.length > 0 && (
          <Card>
            <Table<AuditEvent>
              rowKey={(event, index) =>
                `${event.occurred_at}-${event.action}-${index}`
              }
              size="small"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={visible}
              columns={[
                {
                  title: "Lúc",
                  dataIndex: "occurred_at",
                  render: (value: string) => formatDateTime(value),
                },
                {
                  title: "Ai",
                  key: "actor",
                  // Support staff are no member of the customer's, so the
                  // name alone would not say the support team acted.
                  render: (_, event) => (
                    <Flex wrap gap="small" align="center">
                      <span>{actorName(event)}</span>
                      {event.actor_kind === "support" && <Tag>Đội hỗ trợ</Tag>}
                    </Flex>
                  ),
                },
                {
                  title: "Thao tác",
                  dataIndex: "action",
                  render: (value: string) => {
                    const action = ACTIONS[value] ?? OTHER_ACTION;
                    return <Tag color={action.color}>{action.label}</Tag>;
                  },
                },
                {
                  title: "Bản ghi",
                  key: "resource",
                  render: (_, event) => {
                    const grant = detailText(event, GRANT_DETAIL);
                    return (
                      <Flex vertical>
                        <Typography.Text type="secondary" className="text-xs">
                          {event.resource_type}
                        </Typography.Text>
                        <Typography.Text code className="text-xs">
                          {event.resource_id}
                        </Typography.Text>
                        {grantId == null && grant != null && (
                          <Link href={grantHref(grant)}>
                            Chỉ xem quyền hỗ trợ này
                          </Link>
                        )}
                      </Flex>
                    );
                  },
                },
                {
                  title: "Quyết định chính sách",
                  dataIndex: "policy_decision",
                  render: (value: string | null) => value ?? "—",
                },
                {
                  title: "Mã truy vết",
                  dataIndex: "trace_id",
                  render: (value: string | null) =>
                    value ? (
                      <Typography.Text code>{value}</Typography.Text>
                    ) : (
                      "—"
                    ),
                },
                {
                  title: "Chi tiết",
                  dataIndex: "details",
                  ellipsis: true,
                  width: 260,
                  render: (value: AuditEvent["details"]) =>
                    Object.keys(value).length > 0 ? JSON.stringify(value) : "—",
                },
              ]}
            />
          </Card>
        )}
        {!loading && error == null && (
          <LoadMore
            hasMore={hasMore}
            loading={loadingMore}
            onLoadMore={loadMore}
            shown={items.length}
            noun="sự kiện"
            filtered={filter.length > 0}
          />
        )}
      </Flex>
    </div>
  );
}
