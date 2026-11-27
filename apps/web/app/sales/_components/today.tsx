"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button, Card, Dropdown, Space, Tag, theme, Typography } from "antd";
import { ClockCircleOutlined, RobotOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { unopenedSources, useServedRevision } from "../_lib/served";
import { slaOf } from "../_lib/sla";
import { useAction } from "../_lib/use-action";
import { onHeldOrder, type Viewer } from "../_lib/order-actions";
import { useResource } from "../_lib/use-resource";
import { useSalesViewer } from "../_lib/viewer";
import { OrderActions } from "../orders/[caseId]/actions";
import { QuoteActions } from "../quotes/[caseId]/actions";
import { ApprovalPanel } from "../quotes/[caseId]/approval";
import { SendPanel, SIGNABLE } from "../quotes/[caseId]/send-panel";
import { CandidatePicker } from "../orders/[caseId]/candidate-picker";
import { useOrderChatOffers } from "../orders/[caseId]/chat-offers";
import { needsCode, PickCodeButton } from "../orders/[caseId]/lines";
import { useOrderSource } from "../orders/[caseId]/order-source";
import { useQuoteChatOffers } from "../quotes/[caseId]/chat-offers";
import { useCaseArtifacts } from "./artifacts-panel";
import { ItemCaseChat } from "./case-chat";
import { GuardedButton } from "./guarded-button";
import { MappingTag } from "./tags";

type Today = SalesSchemas["TodayView"];
type Reminder = SalesSchemas["ReminderView"];
type WorkItem = SalesSchemas["WorkItem"];
type Order = SalesSchemas["OrderCaseView"];

/**
 * The SLA of one item (tickets 47, 48): how long is left, or how long it is
 * late, against the server's times; the absolute time on the second line.
 */
export function SlaText({ item, now }: { item: WorkItem; now: number }) {
  const { token } = theme.useToken();
  const sla = slaOf(item, now);
  if (sla.state === "none") return <span>Không đặt hạn</span>;
  const colour =
    sla.state === "late"
      ? token.colorErrorText
      : sla.state === "soon"
        ? token.colorWarningText
        : undefined;
  return (
    <span className="flex flex-col items-end text-end">
      <Typography.Text
        strong={!!colour}
        style={colour ? { color: colour } : undefined}
      >
        {colour ? <ClockCircleOutlined aria-hidden className="me-1" /> : null}
        {sla.relative}
      </Typography.Text>
      <Typography.Text type="secondary">{sla.absolute}</Typography.Text>
    </span>
  );
}

/**
 * Today's morning brief, on top (ticket 47): DW1's opening as it wrote it,
 * marked as DW1's; the counts behind "Xem số liệu". Nothing at all before
 * the brief of the day has been sent.
 */
export function TodayBrief({ today }: { today: Today | null }) {
  const [open, setOpen] = useState(false);
  const brief = today?.brief;
  if (!brief) return null;
  return (
    <Card
      size="small"
      title="Tóm tắt sáng"
      extra={
        <Typography.Text type="secondary">
          {formatDateTime(brief.at)}
        </Typography.Text>
      }
    >
      <Space orientation="vertical" size="small" className="w-full">
        {brief.opening ? (
          <Typography.Paragraph className="mb-0">
            <Tag icon={<RobotOutlined aria-hidden />}>DW1 viết</Tag>
            {brief.opening}
          </Typography.Paragraph>
        ) : null}
        {open ? (
          <ul className="m-0 ps-5">
            {brief.counts.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
        <Button
          type="link"
          className="px-0"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Ẩn số liệu" : "Xem số liệu"}
        </Button>
      </Space>
    </Card>
  );
}

const TERM_REASON = "Nhắc theo hạn của khách không ẩn được";
// "Nhắc lại sau": in how many hours.
const LATER = [
  { key: "1", label: "Sau 1 giờ" },
  { key: "4", label: "Sau 4 giờ" },
  { key: "24", label: "Ngày mai" },
];

/**
 * The day's reminders (ticket 47), each one line with one way to open it and
 * three answers: "Đã xử lý", "Nhắc lại sau", "Không cần". A customer's term
 * takes "Đã xử lý" only (the server refuses the others too).
 */
export function TodayReminders({
  today,
  loading,
  error,
  onRetry,
  onChanged,
  focusCase,
}: {
  today: Today | null;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  onChanged: (next: Today) => void;
  /** The case a deep link names: its reminders are marked. */
  focusCase: string | null;
}) {
  const { run, pending } = useAction();
  const [failed, setFailed] = useState<{ id: string; error: unknown } | null>(
    null,
  );

  const mark = async (
    reminder: Reminder,
    body: { mark: "done" | "dismissed" | "snoozed"; hours?: number },
    said: string,
  ) => {
    const result = await run(
      `reminder:${reminder.notification_id}`,
      body,
      (key) => salesApi().markReminder(reminder.notification_id, body, key),
      said,
    );
    if (result.ok) {
      setFailed(null);
      onChanged(result.value);
    } else setFailed({ id: reminder.notification_id, error: result.error });
  };

  const items = today?.reminders ?? [];
  return (
    <Card size="small" title="Nhắc việc" id="nhac-viec">
      {error ? (
        <LoadError error={error} onRetry={onRetry} />
      ) : loading && !today ? (
        <RegionState kind="loading" />
      ) : (
        <Space orientation="vertical" className="w-full">
          {items.length === 0 ? (
            <Typography.Text>
              Không có nhắc việc nào đang chờ bạn.
            </Typography.Text>
          ) : null}
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {items.map((reminder) => {
              const busy = pending === `reminder:${reminder.notification_id}`;
              const term = reminder.customer_term;
              const focused =
                focusCase !== null && reminder.case_id === focusCase;
              return (
                <li
                  key={reminder.notification_id}
                  aria-current={focused ? "true" : undefined}
                >
                  <Space orientation="vertical" size={4} className="w-full">
                    <span className="flex flex-wrap items-center gap-2">
                      {reminder.link ? (
                        <Link href={reminder.link}>{reminder.title}</Link>
                      ) : (
                        <Typography.Text>{reminder.title}</Typography.Text>
                      )}
                      {term ? (
                        <StatusTag tone="warn">Hạn của khách</StatusTag>
                      ) : null}
                      <Typography.Text type="secondary">
                        {formatDateTime(reminder.at)}
                      </Typography.Text>
                    </span>
                    <Typography.Paragraph
                      className="mb-0"
                      ellipsis={{ rows: 1, expandable: true, symbol: "Xem" }}
                    >
                      {reminder.body}
                    </Typography.Paragraph>
                    <span className="flex flex-wrap gap-2">
                      <Button
                        size="small"
                        loading={busy}
                        onClick={() =>
                          void mark(
                            reminder,
                            { mark: "done" },
                            "Đã đánh dấu đã xử lý",
                          )
                        }
                      >
                        Đã xử lý
                      </Button>
                      {term ? (
                        <GuardedButton
                          size="small"
                          reason={TERM_REASON}
                          inlineReason={false}
                        >
                          Nhắc lại sau
                        </GuardedButton>
                      ) : (
                        <Dropdown
                          trigger={["click"]}
                          menu={{
                            items: LATER,
                            onClick: ({ key }) =>
                              void mark(
                                reminder,
                                { mark: "snoozed", hours: Number(key) },
                                "Sẽ nhắc lại",
                              ),
                          }}
                        >
                          <Button size="small" disabled={busy}>
                            Nhắc lại sau
                          </Button>
                        </Dropdown>
                      )}
                      <GuardedButton
                        size="small"
                        reason={term ? TERM_REASON : null}
                        inlineReason={false}
                        disabled={busy}
                        onClick={() =>
                          void mark(
                            reminder,
                            { mark: "dismissed" },
                            "Đã bỏ qua nhắc này",
                          )
                        }
                      >
                        Không cần
                      </GuardedButton>
                    </span>
                    {failed?.id === reminder.notification_id ? (
                      <ActionError error={failed.error} />
                    ) : null}
                  </Space>
                </li>
              );
            })}
          </ul>
          {today?.hidden ? (
            <Typography.Text type="secondary">
              {`${today.hidden} nhắc bạn đã xử lý, hoãn hoặc bỏ qua không hiện ở đây.`}
            </Typography.Text>
          ) : null}
        </Space>
      )}
    </Card>
  );
}

/**
 * The decision of one waiting item, in its row (ticket 48): the case page's
 * own buttons, with the case's own rules (`OrderActions`, `QuoteActions`,
 * the quotation's send and approval panels), so nothing is decided twice,
 * and the case's own conversation a button away (ticket 79).
 * What needs the source opened says so and links to it; a mail is decided in
 * the inbox, linked at the message.
 */
export function InlineDecision({
  item,
  onChanged,
}: {
  item: WorkItem;
  onChanged: () => void;
}) {
  if (item.kind === "order")
    return <OrderDecision caseId={item.id} onChanged={onChanged} />;
  if (item.kind === "quote")
    return <QuoteDecision caseId={item.id} onChanged={onChanged} />;
  return (
    <Link href={`/sales/inbox?message=${encodeURIComponent(item.id)}`}>
      Mở thư trong Hộp thư để xử lý
    </Link>
  );
}

/** How many lines needing a code the item lists; the rest are on the case. */
const CODES_SHOWN = 5;

/**
 * The lines of an order still waiting for their PRV code, in its item
 * (ticket 79): each with the lines table's own "Chọn mã" and the candidate
 * picker behind it, one line at a time (ui-quality §7). It says how many
 * remain, lists the first few and sends the rest to the case, and after a
 * code is confirmed moves focus to the next line's button.
 */
function CodesToPick({
  order,
  viewer,
  onChanged,
  onOpenSource,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  const [picking, setPicking] = useState<number | null>(null);
  const list = useRef<HTMLUListElement>(null);
  // Set by a decision; the order read again after it moves focus on.
  const advance = useRef(false);
  useEffect(() => {
    if (!advance.current) return;
    advance.current = false;
    // A rejected candidate keeps the picker open on the same line.
    if (picking !== null) return;
    list.current
      ?.querySelector<HTMLButtonElement>("button:not([disabled])")
      ?.focus();
    // Only a new version of the case moves focus, never a re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order.case_version]);
  const lines = order.lines.filter((line) => needsCode(order, line));
  if (lines.length === 0) return null;
  const shown = lines.slice(0, CODES_SHOWN);
  return (
    <section aria-label="Dòng chưa có mã PRV">
      <Typography.Text strong>
        {`${lines.length} dòng chưa có mã PRV`}
      </Typography.Text>
      <ul ref={list} className="m-0 flex list-none flex-col gap-2 p-0 pt-2">
        {shown.map((line) => {
          const typed = line.corrections.find(
            (c) => c.field === "customer_item_code",
          );
          return (
            <li
              key={line.line_no}
              className="flex flex-wrap items-center gap-2"
            >
              <Typography.Text>
                {`Dòng ${line.line_no} · ${typed ? String(typed.value) : line.customer_item_code}`}
              </Typography.Text>
              <MappingTag status={line.mapping.status} />
              {order.design_requests.some((r) => r.line_no === line.line_no) ? (
                <StatusTag tone="warn">Chờ Design</StatusTag>
              ) : null}
              <PickCodeButton
                order={order}
                line={line}
                viewer={viewer}
                onPick={setPicking}
              />
            </li>
          );
        })}
      </ul>
      {lines.length > shown.length ? (
        <Link href={`/sales/orders/${order.case_id}`}>
          {`Còn ${lines.length - shown.length} dòng chưa có mã · Mở hồ sơ`}
        </Link>
      ) : null}
      {picking !== null ? (
        <CandidatePicker
          order={order}
          lineNo={picking}
          onClose={() => setPicking(null)}
          onDone={() => {
            advance.current = true;
            onChanged();
          }}
          onOpenSource={onOpenSource}
        />
      ) : null}
    </section>
  );
}

function OrderDecision({
  caseId,
  onChanged,
}: {
  caseId: string;
  onChanged: () => void;
}) {
  const signedIn = useSalesViewer();
  const order = useResource(
    `sales/order/${caseId}`,
    useCallback(() => salesApi().order(caseId), [caseId]),
  );
  const artifacts = useCaseArtifacts("order", caseId, order.data?.case_version);
  // The case page's own controls for a step asked in the item's chat.
  const offers = useOrderChatOffers(
    caseId,
    order.data?.status,
    artifacts.data?.available,
  );
  const changed = useCallback(() => {
    order.reload();
    onChanged();
  }, [order, onChanged]);
  // A source opened from here (the candidate picker's) is seen at once by
  // the source gate of the buttons above.
  useServedRevision();
  const source = useOrderSource(order.data);
  if (order.loading) return <RegionState kind="loading" />;
  if (order.error || !order.data)
    return <LoadError error={order.error} onRetry={order.reload} />;
  // Seen only through its NOC/ESF hold (ticket 78): read and the hold, as
  // on the case page, so no control the server refuses is drawn enabled.
  const viewer = order.data.export_hold_only ? onHeldOrder(signedIn) : signedIn;
  const { labels } = unopenedSources(order.data);
  return (
    <Space orientation="vertical" className="w-full">
      <OrderActions
        order={order.data}
        viewer={viewer}
        sourceOpened={labels.length === 0}
        onChanged={changed}
      />
      <CodesToPick
        order={order.data}
        viewer={viewer}
        onChanged={changed}
        onOpenSource={source.open}
      />
      <ItemCaseChat
        onCase={{ kind: "order", caseId }}
        offers={offers}
        onDecided={changed}
      />
      {labels.length ? (
        // The button above says why; this says where.
        <Link href={`/sales/orders/${caseId}`}>
          Mở hồ sơ để xem nguồn ({labels.join(", ")})
        </Link>
      ) : (
        <Link href={`/sales/orders/${caseId}`}>Mở hồ sơ</Link>
      )}
      {source.drawers(viewer)}
    </Space>
  );
}

function QuoteDecision({
  caseId,
  onChanged,
}: {
  caseId: string;
  onChanged: () => void;
}) {
  const viewer = useSalesViewer();
  const quote = useResource(
    `sales/quote/${caseId}`,
    useCallback(() => salesApi().quote(caseId), [caseId]),
  );
  const artifacts = useCaseArtifacts("quote", caseId, quote.data?.case_version);
  const offers = useQuoteChatOffers(caseId, quote.data?.status);
  const changed = useCallback(() => {
    quote.reload();
    onChanged();
  }, [quote, onChanged]);
  if (quote.loading) return <RegionState kind="loading" />;
  if (quote.error || !quote.data)
    return <LoadError error={quote.error} onRetry={quote.reload} />;
  const data = quote.data;
  const files = artifacts.data?.artifacts ?? [];
  return (
    <Space orientation="vertical" className="w-full">
      <QuoteActions quote={data} viewer={viewer} onDone={changed} />
      {SIGNABLE.has(data.status) ? (
        <SendPanel quote={data} artifacts={files} onChanged={changed} />
      ) : null}
      {data.status === "pending_approval" ? (
        <ApprovalPanel
          quote={data}
          viewer={viewer}
          artifacts={files}
          onDone={changed}
        />
      ) : null}
      <ItemCaseChat
        onCase={{ kind: "quote", caseId }}
        offers={offers}
        onDecided={changed}
      />
      <Link href={`/sales/quotes/${caseId}`}>Mở hồ sơ</Link>
    </Space>
  );
}
