"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Key,
} from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button, Empty, Space, Table, Typography } from "antd";
import {
  PaperClipOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  StopOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { RegionState } from "../../../components/region-state";
import { useAuth } from "../../../lib/auth/auth-context";
import {
  formatAge,
  formatDateTime,
  instantMs,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { compareVi, matches } from "../../../lib/search";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { label, ROUTING_REASON } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { useListView } from "../_lib/use-status-filter";
import { salesCrumbs } from "../_components/crumbs";
import { GuardedButton } from "../_components/guarded-button";
import {
  Assignee,
  ListToolbar,
  listFooter,
  PriorityPanel,
  RowTitle,
  type PriorityItem,
} from "../_components/list-parts";
import { SCOPE, useSalesFrame } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { MessageDispositionTag } from "../_components/tags";

type Message = SalesSchemas["InboxMessageView"];

/** The tabs: the disposition a message ended in (CONTEXT.md). */
const GROUP: Record<string, readonly string[]> = {
  waiting: ["not_yet_processed"],
  routed: ["routed_to_sales"],
  cased: ["case_created", "attached_to_case"],
};
const TABS = ["all", "waiting", "routed", "cased"] as const;
type Tab = (typeof TABS)[number];
const SORTS = ["newest", "oldest", "sender"] as const;

const inTab = (tab: Tab, m: Message) =>
  tab === "all" || GROUP[tab]!.includes(m.disposition.kind);

/**
 * Hộp thư (mock): every sample message with the one disposition it ended in,
 * the reason and the owner of a message routed to Sales, and "DW xử lý" per
 * message or for all. The mock inbox stands in for a mailbox; processing
 * starts from the button. A message's link (`?message=`) opens it here.
 */
export default function InboxPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Inbox />
      </Suspense>
    </ScopeGate>
  );
}

function Inbox() {
  const now = useNow();
  const { hasScope } = useAuth();
  const { paused, overview } = useSalesFrame();
  const focus = useSearchParams().get("message");
  const name = usePeople();
  const view = useListView(TABS, "all", SORTS, "newest");
  const inbox = useResource(
    "sales/inbox",
    useCallback(() => salesApi().inbox(), []),
  );
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [expanded, setExpanded] = useState<readonly Key[]>(
    focus ? [focus] : [],
  );
  useEffect(() => {
    if (focus)
      setExpanded((keys) => (keys.includes(focus) ? keys : [...keys, focus]));
  }, [focus]);

  const messages = useMemo(() => inbox.data ?? [], [inbox.data]);
  const waiting = messages.filter(
    (m) => m.disposition.kind === "not_yet_processed",
  ).length;
  const routed = messages.filter(
    (m) => m.disposition.kind === "routed_to_sales",
  );
  const ownerless = routed.filter((m) => !m.disposition.owner);
  const unverified = messages.filter((m) => !m.sender_verified);

  const shown = (() => {
    const rows = messages
      .filter((m) => inTab(view.tab, m))
      .filter((m) =>
        matches(view.query, [
          m.message_id,
          m.subject,
          m.sender,
          m.sender_name,
          ...m.attachments.map((a) => a.name),
        ]),
      );
    const at = (m: Message) => instantMs(m.received_at) ?? 0;
    if (view.sort === "oldest") return [...rows].sort((a, b) => at(a) - at(b));
    if (view.sort === "sender")
      return [...rows].sort((a, b) => compareVi(a.sender_name, b.sender_name));
    return [...rows].sort((a, b) => at(b) - at(a));
  })();
  const filtered = view.tab !== "all" || view.query !== "";

  const processReason = !hasScope(SCOPE.inbox)
    ? "Bạn không có quyền cho DW1 xử lý thư (cần quyền xử lý hộp thư của Sales)."
    : paused
      ? "DW1 đang tạm dừng: chỉ Trưởng bộ phận Sales cho DW1 chạy lại."
      : null;

  const after = (result: { ok: boolean; error?: unknown }) => {
    if (result.ok) {
      setError(null);
      inbox.reload();
      overview.reload();
    } else setError(result.error);
  };

  const processAll = async () =>
    after(
      await run(
        "inbox/all",
        null,
        (key) => salesApi().processAll(key),
        "DW1 đã xử lý các thư đang chờ",
      ),
    );

  const processOne = async (message: Message) =>
    after(
      await run(
        `inbox/${message.message_id}`,
        null,
        (key) => salesApi().processMessage(message.message_id, key),
        `DW1 đã xử lý thư ${message.message_id}`,
      ),
    );

  const priority: PriorityItem[] = [];
  if (waiting)
    priority.push({
      key: "waiting",
      tone: "pri",
      lead: `${waiting} thư chưa xử lý`,
      text: "DW1 xử lý khi bạn bấm “DW xử lý”.",
      href: "/sales/inbox?tab=waiting",
    });
  if (ownerless.length)
    priority.push({
      key: "ownerless",
      tone: "err",
      lead: `${ownerless.length} thư chuyển Sales chưa có người phụ trách`,
      text: ownerless[0]!.subject,
      href: `/sales/inbox?tab=routed&message=${encodeURIComponent(ownerless[0]!.message_id)}`,
    });
  else if (routed.length)
    priority.push({
      key: "routed",
      tone: "warn",
      lead: `${routed.length} thư chuyển Sales xử lý`,
      text: "mỗi thư có lý do và người phụ trách",
      href: "/sales/inbox?tab=routed",
    });
  if (unverified.length)
    priority.push({
      key: "unverified",
      tone: "warn",
      lead: `${unverified.length} thư chưa xác thực người gửi`,
      text: unverified
        .slice(0, 2)
        .map((m) => m.sender)
        .join(", "),
    });

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Hộp thư")}
        title="Hộp thư (giả lập)"
        description={
          inbox.data
            ? `${messages.length} thư · ${waiting} chưa xử lý · ${routed.length} chuyển Sales. Mỗi thư kết thúc ở đúng một hướng xử lý; thư chuyển Sales có lý do và người phụ trách.`
            : "Thư mẫu kèm PO, yêu cầu báo giá và phản hồi của Design. Mỗi thư kết thúc ở đúng một hướng xử lý; thư chuyển Sales có lý do và người phụ trách."
        }
        extra={
          <GuardedButton
            type="primary"
            icon={<RobotOutlined aria-hidden />}
            loading={pending === "inbox/all"}
            reason={
              processReason ??
              (inbox.data && waiting === 0
                ? "Mọi thư đã có hướng xử lý."
                : null)
            }
            onClick={processAll}
          >
            DW xử lý tất cả ({waiting})
          </GuardedButton>
        }
      />
      <ActionError error={error} />
      {inbox.error ? (
        <RegionState error={inbox.error} onRetry={inbox.reload} />
      ) : (
        <>
          {inbox.data ? (
            <PriorityPanel
              items={priority}
              calm="Mọi thư đã có hướng xử lý và người phụ trách."
            />
          ) : null}
          <ListToolbar
            tabs={[
              { value: "all", label: "Tất cả", count: messages.length },
              { value: "waiting", label: "Chưa xử lý", count: waiting },
              { value: "routed", label: "Chuyển Sales", count: routed.length },
              {
                value: "cased",
                label: "Đã vào hồ sơ",
                count: messages.filter((m) => inTab("cased", m)).length,
              },
            ]}
            tab={view.tab}
            onTab={view.setTab}
            query={view.query}
            onQuery={view.setQuery}
            placeholder="Tiêu đề, người gửi, tên tệp"
            sorts={[
              { value: "newest", label: "Mới nhất" },
              { value: "oldest", label: "Cũ nhất" },
              { value: "sender", label: "Người gửi (A–Z)" },
            ]}
            sort={view.sort}
            onSort={view.setSort}
          />
          <Table<Message>
            rowKey="message_id"
            loading={inbox.loading}
            dataSource={shown}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            rowClassName={(m) =>
              m.message_id === focus ? "ant-table-row-selected" : ""
            }
            expandable={{
              expandedRowKeys: expanded,
              onExpandedRowsChange: setExpanded,
              expandedRowRender: (m) => (
                <div className="max-w-3xl space-y-2">
                  {m.attachments.length ? (
                    <Space wrap>
                      {m.attachments.map((a) => (
                        <Typography.Text key={a.attachment_id}>
                          <PaperClipOutlined aria-hidden /> {a.name}
                        </Typography.Text>
                      ))}
                    </Space>
                  ) : null}
                  {m.disposition.detail ? (
                    <Typography.Paragraph className="!mb-0">
                      <Typography.Text strong>
                        Ghi chú của DW1:{" "}
                      </Typography.Text>
                      {m.disposition.detail}
                    </Typography.Paragraph>
                  ) : null}
                  <Typography.Paragraph className="!mb-0 whitespace-pre-wrap">
                    {m.body_text}
                  </Typography.Paragraph>
                </div>
              ),
              expandRowByClick: false,
            }}
            locale={{
              emptyText: inbox.loading ? (
                " "
              ) : filtered && messages.length ? (
                <Empty description="Không có thư nào khớp bộ lọc.">
                  <Button
                    onClick={() => {
                      view.setQuery("");
                      view.setTab("all");
                    }}
                  >
                    Xóa bộ lọc
                  </Button>
                </Empty>
              ) : (
                "Hộp thư giả lập không có thư nào cho không gian làm việc này."
              ),
            }}
            footer={() =>
              `${listFooter(shown.length, messages.filter((m) => inTab(view.tab, m)).length, messages.length, "thư", view.query !== "")} · ${waiting} chưa xử lý`
            }
            columns={[
              {
                title: "Thư",
                key: "subject",
                render: (_, m) => (
                  <RowTitle
                    href={`/sales/inbox?message=${encodeURIComponent(m.message_id)}`}
                    title={m.subject}
                    code={m.message_id}
                    sub={
                      <>
                        {m.sender_name} &lt;{m.sender}&gt;
                        {m.attachments.length ? (
                          <>
                            {" · "}
                            <PaperClipOutlined aria-hidden />{" "}
                            {m.attachments.length} tệp
                          </>
                        ) : null}
                      </>
                    }
                  />
                ),
              },
              {
                title: "Người gửi",
                key: "verified",
                render: (_, m) =>
                  m.sender_verified ? (
                    <StatusTag
                      tone="ok"
                      icon={<SafetyCertificateOutlined aria-hidden />}
                    >
                      Đã xác thực người gửi
                    </StatusTag>
                  ) : (
                    <StatusTag
                      tone="warn"
                      icon={<WarningOutlined aria-hidden />}
                    >
                      Chưa xác thực người gửi
                    </StatusTag>
                  ),
              },
              {
                title: "Hướng xử lý",
                key: "disposition",
                render: (_, m) => (
                  <span className="flex flex-col items-start gap-1">
                    <MessageDispositionTag kind={m.disposition.kind} />
                    {m.disposition.reason ? (
                      <Typography.Text type="secondary">
                        Lý do: {label(ROUTING_REASON, m.disposition.reason)}
                      </Typography.Text>
                    ) : null}
                    {m.disposition.case_id ? (
                      <Link
                        href={`/sales/${m.disposition.case_kind === "quote" ? "quotes" : "orders"}/${m.disposition.case_id}`}
                      >
                        {m.disposition.case_kind === "quote"
                          ? "Mở báo giá"
                          : "Mở đơn hàng"}
                      </Link>
                    ) : null}
                  </span>
                ),
              },
              {
                title: "Người phụ trách",
                key: "owner",
                align: "center",
                render: (_, m) =>
                  m.disposition.kind === "routed_to_sales" ? (
                    m.disposition.owner ? (
                      <Assignee
                        name={name(m.disposition.owner)}
                        group={m.disposition.owner.startsWith("role:")}
                      />
                    ) : (
                      <StatusTag tone="err" icon={<StopOutlined aria-hidden />}>
                        Chưa có người phụ trách
                      </StatusTag>
                    )
                  ) : (
                    ""
                  ),
              },
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                key: "received",
                align: "right",
                render: (_, m) => (
                  <span className="flex flex-col items-end">
                    <span>{formatAge(m.received_at, now)} trước</span>
                    <Typography.Text type="secondary">
                      {formatDateTime(m.received_at, { zoneLabel: false })}
                    </Typography.Text>
                  </span>
                ),
              },
              {
                title: "DW1",
                key: "process",
                fixed: "right",
                render: (_, m) =>
                  m.disposition.kind === "not_yet_processed" ? (
                    <GuardedButton
                      size="small"
                      inlineReason={false}
                      reason={processReason}
                      loading={pending === `inbox/${m.message_id}`}
                      onClick={() => processOne(m)}
                      aria-label={`DW xử lý thư ${m.message_id}`}
                    >
                      DW xử lý
                    </GuardedButton>
                  ) : m.disposition.processed_at ? (
                    <span className="flex flex-col items-start">
                      <Typography.Text type="secondary">
                        đã xử lý
                      </Typography.Text>
                      <Typography.Text type="secondary">
                        {formatDateTime(m.disposition.processed_at, {
                          zoneLabel: false,
                        })}
                      </Typography.Text>
                      {/* A Design reply processed before its YCBG went to
                          Design is matched once it has: the API takes a
                          routed message again (InboxService.process). */}
                      {m.disposition.reason === "design_reply_unmatched" ? (
                        <GuardedButton
                          size="small"
                          inlineReason={false}
                          reason={processReason}
                          loading={pending === `inbox/${m.message_id}`}
                          onClick={() => processOne(m)}
                          aria-label={`DW xử lý lại thư ${m.message_id}`}
                        >
                          DW xử lý lại
                        </GuardedButton>
                      ) : null}
                    </span>
                  ) : null,
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
