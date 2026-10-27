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
import { formatDateTime, TIME_ZONE_LABEL } from "../../lib/dates";
import { apiClient } from "../../lib/session";
import { useCachedPages } from "../../lib/use-cached-pages";
import { useFillHeight } from "../../lib/use-fill-height";

const ACTIONS: Record<string, { label: string; color: string }> = {
  "run.started": { label: "Bắt đầu lượt chạy", color: "processing" },
  "run.waiting_approval": { label: "Chờ duyệt", color: "warning" },
  "run.resumed": { label: "Chạy tiếp", color: "processing" },
  "run.completed": { label: "Xong lượt chạy", color: "success" },
  "approval.decided": { label: "Đã quyết yêu cầu", color: "success" },
  "tool.executed": { label: "Đã chạy công cụ", color: "default" },
  "run.failed": { label: "Lượt chạy lỗi", color: "error" },
  // PLUG-IN POINT: a bounded context adds its own actions here. An unmapped
  // action still shows, as "Hoạt động hệ thống" — a row is never dropped.
  // Sales (DW1): every action its services and lanes audit (2026-10-27).
  "sales.mail.stored": { label: "Nhận thư vào hộp thư", color: "default" },
  "sales.message.queued": { label: "Xếp thư chờ xử lý", color: "default" },
  "sales.message.queued_by_lane": {
    label: "DW1 xếp thư chờ xử lý",
    color: "default",
  },
  "sales.message.processed": { label: "Xử lý thư", color: "default" },
  "sales.message.processing_done": {
    label: "Xử lý thư xong",
    color: "success",
  },
  "sales.message.processing_failed": { label: "Xử lý thư lỗi", color: "error" },
  "sales.order.checked": { label: "Kiểm tra đơn", color: "default" },
  "sales.order.review_started": {
    label: "Bắt đầu tự kiểm đơn",
    color: "processing",
  },
  "sales.order.finding_disposed": {
    label: "Xử lý cờ của đơn",
    color: "default",
  },
  "sales.order.prepared": { label: "Chuẩn bị đơn xong", color: "processing" },
  "sales.order.bravo_recorded": {
    label: "Ghi số đơn Bravo",
    color: "processing",
  },
  "sales.order.cross_checked": { label: "Kiểm chéo đơn", color: "success" },
  "sales.order.confirmed": { label: "Xác nhận đơn", color: "success" },
  "sales.order.correction_requested": {
    label: "Yêu cầu khách sửa PO",
    color: "warning",
  },
  "sales.order.revised": { label: "PO sửa đổi", color: "default" },
  "sales.order.reassigned": { label: "Giao lại đơn", color: "default" },
  "sales.order.closed": { label: "Đóng đơn", color: "default" },
  "sales.quote.received": { label: "Nhận yêu cầu báo giá", color: "default" },
  "sales.quote.ycbg_drafted": { label: "Soạn YCBG", color: "default" },
  "sales.quote.ycbg_recorded": {
    label: "Ghi YCBG trên Bravo",
    color: "processing",
  },
  "sales.quote.sent_to_design": { label: "Gửi Design", color: "processing" },
  "sales.quote.design_replied": {
    label: "Design phản hồi",
    color: "processing",
  },
  "sales.quote.finding_answered": {
    label: "Trả lời cờ báo giá",
    color: "default",
  },
  "sales.quote.priced": { label: "Định giá", color: "processing" },
  "sales.quote.submitted": { label: "Gửi duyệt báo giá", color: "processing" },
  "sales.quote.approved": { label: "Duyệt báo giá", color: "success" },
  "sales.quote.returned": { label: "Trả lại định giá", color: "warning" },
  "sales.artifact.rendered": { label: "Tạo tệp", color: "default" },
  "sales.artifact.downloaded": { label: "Tải tệp", color: "default" },
  "sales.rules.proposed": { label: "Đề xuất quy tắc", color: "processing" },
  "sales.rules.approved": { label: "Duyệt quy tắc", color: "success" },
  "sales.followup.sent": { label: "Gửi nhắc việc", color: "default" },
  "sales.worker.paused": { label: "Tạm dừng DW1", color: "warning" },
  "sales.worker.resumed": { label: "Chạy lại DW1", color: "processing" },
};

/** The background lanes that audit as themselves (ADR 0011), by worker
 * registry name, as `details.actor` names them: `system:<lane>`. */
const LANES: Record<string, string> = {
  sales_mail_drop: "DW1 · đọc thư mục thư",
  sales_inbox: "DW1 · nhận thư mới",
  sales_processing: "DW1 · xử lý thư",
  sales_followups: "DW1 · nhắc việc",
  sales_rule_drafts: "DW1 · nháp quy tắc",
};
const OTHER_ACTION = { label: "Hoạt động hệ thống", color: "default" };

/** The key a support grant's events carry their grant under (ADR 0024). */
const GRANT_DETAIL = "support_grant_id";

function detailText(event: AuditEvent, key: string): string | null {
  const value = event.details[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Who did it, as the server names them today; a background lane by what
 * it does (its `system:<lane>` actor), and anyone else with no name by a
 * short id. */
function actorName(event: AuditEvent): string {
  if (event.actor_display_name) return event.actor_display_name;
  const actor = detailText(event, "actor");
  if (actor?.startsWith("system:")) {
    const lane = actor.slice("system:".length);
    return LANES[lane] ?? `Tác vụ nền (${lane})`;
  }
  return `${event.actor_id.slice(0, 8)}…`;
}

/** A long record id (a stored mail's 68-character hash) shortened for the
 * row; the whole id stays copyable and searchable. */
function shortId(id: string): string {
  return id.length > 24 ? `${id.slice(0, 16)}…` : id;
}

/** The details as "key: value", without what the row already shows (the
 * actor) and without empty values. */
function detailsText(details: AuditEvent["details"]): string {
  const parts = Object.entries(details)
    .filter(([key, value]) => key !== "actor" && value !== null && value !== "")
    .map(
      ([key, value]) =>
        `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`,
    );
  return parts.length > 0 ? parts.join(" · ") : "—";
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
  const fill = useFillHeight();
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
              ref={fill.tableRef}
              scroll={{ x: "max-content", y: fill.y }}
              dataSource={visible}
              columns={[
                {
                  title: `Lúc (${TIME_ZONE_LABEL})`,
                  dataIndex: "occurred_at",
                  render: (value: string) =>
                    formatDateTime(value, { zoneLabel: false }),
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
                        <Typography.Text
                          code
                          copyable={{ text: event.resource_id }}
                          title={event.resource_id}
                        >
                          {shortId(event.resource_id)}
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
                  render: (value: AuditEvent["details"]) => detailsText(value),
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
