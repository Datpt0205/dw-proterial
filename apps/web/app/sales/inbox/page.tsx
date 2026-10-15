"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
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
import { LoadError } from "../../../components/load-error";
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
import {
  INTENT_KIND,
  label,
  PROCESSING_ERROR,
  REPLY_KIND,
  ROUTING_REASON,
} from "../_lib/labels";
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
import { MessageDispositionTag, ProcessingTag } from "../_components/tags";
import { HandoffDraft } from "./handoff-draft";

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

/** Queued or running: DW1 has the message (ticket 25), nothing to press. */
const working = (m: Message) =>
  m.processing?.status === "queued" || m.processing?.status === "running";

/** How often the page reads the inbox again while DW1 has work. */
const POLL_MS = 3_000;

/**
 * Hộp thư (mock): every sample message with the one disposition it ended in,
 * the reason and the owner of a message routed to Sales, and "DW xử lý" per
 * message or for all. The mock inbox stands in for a mailbox. A message's link
 * (`?message=`) opens it here.
 *
 * "DW xử lý" queues (ticket 25): the API answers with the job at once and the
 * worker processes it, reading every file in the reader sandbox. While any
 * message is queued or running the page reads the inbox again every few
 * seconds, keeping what is shown, and each row says where its job stands;
 * a job that failed says why, and the button is there to press again.
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
  const busy = messages.filter(working).length;
  // What "DW xử lý tất cả" would queue: waiting, and not with DW1 already.
  const pressable = messages.filter(
    (m) => m.disposition.kind === "not_yet_processed" && !working(m),
  ).length;

  // While DW1 has work, read the inbox again; once it has none, the overview
  // (the nav's counts) once more, for what the work changed.
  const reloadInbox = inbox.reload;
  const reloadOverview = overview.reload;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(reloadInbox, POLL_MS);
    return () => clearInterval(timer);
  }, [busy, reloadInbox]);
  const wasBusy = useRef(false);
  useEffect(() => {
    if (wasBusy.current && !busy) reloadOverview();
    wasBusy.current = busy > 0;
  }, [busy, reloadOverview]);
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

  // A PO no layout read, from a customer: the form is mapped once, by a PIC
  // who sees prices (the form prints them); the server checks both scopes.
  const mapsForm = (m: Message) =>
    m.disposition.reason === "attachment_unreadable" &&
    Boolean(m.disposition.customer_code) &&
    hasScope(SCOPE.prepare) &&
    hasScope(SCOPE.price);

  const processAll = async () =>
    after(
      await run(
        "inbox/all",
        null,
        (key) => salesApi().processAll(key),
        "Đã xếp các thư đang chờ cho DW1 xử lý",
      ),
    );

  const processOne = async (message: Message) =>
    after(
      await run(
        `inbox/${message.message_id}`,
        null,
        (key) => salesApi().processMessage(message.message_id, key),
        `Đã xếp thư ${message.message_id} cho DW1 xử lý`,
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
        subtitle={
          inbox.data
            ? `${messages.length} thư · ${waiting} chưa xử lý${busy ? ` (${busy} DW1 đang xử lý)` : ""} · ${routed.length} chuyển Sales. Mỗi thư kết thúc ở đúng một hướng xử lý; thư chuyển Sales có lý do và người phụ trách.`
            : "Thư mẫu kèm PO, yêu cầu báo giá và phản hồi của Design. Mỗi thư kết thúc ở đúng một hướng xử lý; thư chuyển Sales có lý do và người phụ trách."
        }
        actions={
          <GuardedButton
            type="primary"
            icon={<RobotOutlined aria-hidden />}
            loading={pending === "inbox/all"}
            reason={
              processReason ??
              (inbox.data && pressable === 0
                ? busy
                  ? "DW1 đang xử lý các thư đã xếp, chờ xong rồi xem kết quả."
                  : "Mọi thư đã có hướng xử lý."
                : null)
            }
            onClick={processAll}
          >
            DW xử lý tất cả ({pressable})
          </GuardedButton>
        }
      />
      <ActionError error={error} />
      {inbox.error ? (
        <LoadError error={inbox.error} onRetry={inbox.reload} />
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
                          {mapsForm(m) ? (
                            <>
                              {" · "}
                              <Link
                                href={`/sales/layouts/new?message=${encodeURIComponent(m.message_id)}&attachment=${encodeURIComponent(a.attachment_id)}`}
                              >
                                Thiết lập mẫu PO
                              </Link>
                            </>
                          ) : null}
                        </Typography.Text>
                      ))}
                    </Space>
                  ) : null}
                  {m.disposition.layout_prefill ? (
                    <Typography.Paragraph className="!mb-0">
                      {m.disposition.layout_prefill.outcome === "proposed"
                        ? "Mô hình đã gợi ý cách gán mẫu PO này: mở “Thiết lập mẫu PO” để kiểm và gửi duyệt."
                        : "Mô hình không gợi ý được cách gán mẫu PO này: lập tay ở “Thiết lập mẫu PO”."}
                    </Typography.Paragraph>
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
                  {m.handoff_draft && m.disposition.handoff ? (
                    <HandoffDraft
                      draft={m.handoff_draft}
                      handoff={m.disposition.handoff}
                    />
                  ) : null}
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
                    {m.disposition.reading ? (
                      <IntentTag reading={m.disposition.reading} />
                    ) : null}
                    {m.disposition.reply ? (
                      <ReplyTag reply={m.disposition.reply} />
                    ) : null}
                    {m.handoff_draft ? (
                      <Typography.Text>
                        Có bản chuyển{" "}
                        {m.handoff_draft.to === "qa" ? "QA" : "PC"} soạn sẵn: mở
                        thư để xem
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
                  m.processing && working(m) ? (
                    <span role="status">
                      <ProcessingTag status={m.processing.status} />
                    </span>
                  ) : m.disposition.kind === "not_yet_processed" ? (
                    <span className="flex flex-col items-start gap-1">
                      {m.processing?.status === "failed" ? (
                        <>
                          <ProcessingTag status="failed" />
                          <Typography.Text>
                            {label(PROCESSING_ERROR, m.processing.error)}
                          </Typography.Text>
                        </>
                      ) : null}
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
                    </span>
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

/**
 * What a model read the message as (ticket 31): the kind, beside the reason
 * code routed it with, and the numbers code resolved against the sender's
 * own records, a PO with the one live order case DW1 holds for it as a link
 * to that case. A machine's reading, so it says so.
 */
function IntentTag({
  reading,
}: {
  reading: NonNullable<SalesSchemas["MessageDispositionView"]["reading"]>;
}) {
  if (reading.outcome !== "read" || !reading.kind)
    return (
      <StatusTag tone="unk">Mô hình không đọc được: DW1 không hiểu</StatusTag>
    );
  return (
    <span className="flex flex-col items-start gap-1">
      <StatusTag tone="warn">
        Mô hình đọc: {label(INTENT_KIND, reading.kind)}
      </StatusTag>
      {reading.references.length ? (
        <Typography.Text>
          Nhắc tới:{" "}
          {reading.references.map((r, i) => {
            const name = `${r.record === "purchase_order" ? "PO" : "YCBG/RFQ"} ${r.number}`;
            return (
              <span key={`${r.record}:${r.number}`}>
                {i ? ", " : null}
                {/* The one live order case code resolved the PO to. */}
                {r.order_case_id ? (
                  <Link href={`/sales/orders/${r.order_case_id}`}>{name}</Link>
                ) : (
                  name
                )}
              </span>
            );
          })}
        </Typography.Text>
      ) : null}
    </span>
  );
}

/**
 * A reply its thread headers attached to a case (ticket 32): which message it
 * answers, and what a model read it as where the step is on. The case shows
 * the sentences and the step it proposes; Sales decides there.
 */
function ReplyTag({
  reply,
}: {
  reply: NonNullable<SalesSchemas["MessageDispositionView"]["reply"]>;
}) {
  const reading = reply.reading;
  return (
    <span className="flex flex-col items-start gap-1">
      <Typography.Text>
        Trả lời thư {reply.linked_to} trong luồng
      </Typography.Text>
      {reading ? (
        reading.outcome === "read" && reading.kind ? (
          <StatusTag tone="warn">
            Mô hình đọc: {label(REPLY_KIND, reading.kind)}
          </StatusTag>
        ) : (
          <StatusTag tone="unk">
            Mô hình không đọc được: Sales đọc thư
          </StatusTag>
        )
      ) : null}
    </span>
  );
}
