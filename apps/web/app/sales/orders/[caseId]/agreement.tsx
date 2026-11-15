"use client";

import { useState } from "react";
import Link from "next/link";
import { App, Card, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { InfoTip, StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../../lib/dates";
import { useNow } from "../../../../lib/use-now";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { GuardedButton } from "../../_components/guarded-button";

type Order = SalesSchemas["OrderCaseView"];
type Reply = SalesSchemas["CaseReplyView"];
type Term = NonNullable<NonNullable<Order["confirmation"]>["term"]>;

const PREPARE = "sales.order.prepare";
const NO_SCOPE =
  "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách).";
const IN_LOOP =
  "Khách đang xin thay đổi đơn: ghi câu trả lời của khách ở mục thay đổi.";

const HOW = {
  accepted: "Khách đồng ý bằng lời",
  implied: "Khách im lặng quá hạn: đồng ý ngầm",
} as const;

/** "5 ngày làm việc từ ngày PO": a customer's term of silence, in words. */
function termText(term: Term): string {
  const days = `${term.days} ngày${term.day_count === "business" ? " làm việc (thứ Hai đến thứ Sáu)" : ""}`;
  const from =
    term.counted_from === "po_date" ? "từ ngày PO" : "từ ngày gửi xác nhận";
  return `${days} ${from}`;
}

/** The customer's reply that proposes ``step``: the server marks one at most. */
function proposing(order: Order, step: Reply["proposal"]): Reply | null {
  return order.replies.find((r) => r.proposal === step) ?? null;
}

function MailLink({ id }: { id: string }) {
  return (
    <Link href={`/sales/inbox?message=${encodeURIComponent(id)}`}>
      Xem trong thư
    </Link>
  );
}

/**
 * The confirmation sent, then the customer's answer (ticket 28, dw_sales
 * ADR 0011): the state and how the customer agreed, and while the order
 * waits on them, "Khách đã đồng ý", "Khách im lặng quá hạn → ghi đồng ý
 * ngầm" and "Khách từ chối", each disabled with its reason. A reply DW1 read
 * as agreeing or refusing marks its button "Đề xuất từ luồng thư"; nothing
 * is recorded until a person presses. The term of silence is on click.
 */
export function AgreementPanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const sent = order.confirmation;
  if (!sent) return null;
  return (
    <AgreementCard
      order={order}
      sent={sent}
      viewer={viewer}
      onChanged={onChanged}
    />
  );
}

function AgreementCard({
  order,
  sent,
  viewer,
  onChanged,
}: {
  order: Order;
  sent: NonNullable<Order["confirmation"]>;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const name = usePeople();
  const now = useNow();
  const { modal } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const version = order.case_version;
  const agreed = order.agreement;

  const step = async (
    id: string,
    call: (key: string) => Promise<unknown>,
    done: string,
  ) => {
    const result = await run(id, { version }, call, done);
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  const accepting = proposing(order, "record_accepted");
  const declining = proposing(order, "record_declined");
  const blocked = !viewer.hasScope(PREPARE)
    ? NO_SCOPE
    : order.update_loop
      ? IN_LOOP
      : null;
  const impliedFrom = sent.implied_from ? Date.parse(sent.implied_from) : null;
  const impliedReason =
    blocked ??
    (impliedFrom === null
      ? "Khách này không có số ngày im lặng được coi là đồng ý trong quy tắc."
      : now < impliedFrom
        ? `Chưa hết hạn: được ghi từ ${formatDateTime(sent.implied_from)}.`
        : null);

  const confirmStep = (
    id: string,
    title: string,
    content: string,
    call: (key: string) => Promise<unknown>,
    done: string,
  ) =>
    modal.confirm({
      title,
      content,
      okText: title,
      cancelText: "Chưa ghi",
      autoFocusButton: "cancel",
      onOk: () => step(id, call, done),
    });

  const quotes = accepting?.intents
    .filter((i) => i.intent === "accepts")
    .flatMap((i) => i.quotes);

  return (
    <Card size="small" title="Khách xác nhận đơn">
      <Space orientation="vertical" className="w-full">
        <Space wrap role="status">
          {agreed ? (
            <>
              <StatusTag tone="ok">{HOW[agreed.how]}</StatusTag>
              <Typography.Text>
                {name(agreed.by)} ghi lúc {formatDateTime(agreed.at)}
              </Typography.Text>
              {agreed.message_id ? <MailLink id={agreed.message_id} /> : null}
            </>
          ) : (
            <>
              <StatusTag tone="warn">Đã gửi xác nhận, chờ khách</StatusTag>
              <Typography.Text>
                từ {formatDateTime(sent.sent_at)}
              </Typography.Text>
            </>
          )}
          <InfoTip label="Đồng ý ngầm">
            {sent.term && sent.implied_from
              ? `Khách này im lặng ${termText(sent.term)} được coi là đồng ý: từ ${formatDateTime(sent.implied_from)}. DW1 báo bạn khi đến hạn; chỉ người ghi, DW1 không tự ghi.`
              : "Khách này không có số ngày im lặng được coi là đồng ý (quy tắc kiểm tra PO): chỉ ghi khi khách trả lời."}
            {sent.message_id ? ` Thời điểm gửi lấy từ thư Sales đã gửi.` : ""}
          </InfoTip>
          {sent.message_id ? <MailLink id={sent.message_id} /> : null}
        </Space>

        {agreed?.quotes.length ? (
          <ul className="m-0 pl-5" aria-label="Câu khách viết">
            {agreed.quotes.map((q) => (
              <li key={q}>
                <Typography.Text italic>“{q}”</Typography.Text>
              </li>
            ))}
          </ul>
        ) : null}

        {order.status === "confirmation_sent" ? (
          <Space orientation="vertical" className="w-full">
            {accepting || declining ? (
              <Typography.Paragraph className="!mb-0" role="note">
                <Typography.Text strong>DW1 đề xuất: </Typography.Text>
                {accepting
                  ? "khách đã đồng ý, theo câu trích dưới đây."
                  : "khách không đồng ý."}{" "}
                <MailLink id={(accepting ?? declining)!.message_id} />. Đọc thư
                rồi tự quyết: DW1 không tự ghi.
              </Typography.Paragraph>
            ) : null}
            {quotes?.length ? (
              <ul className="m-0 pl-5" aria-label="Câu khách viết">
                {quotes.map((q) => (
                  <li key={q}>
                    <Typography.Text italic>“{q}”</Typography.Text>
                  </li>
                ))}
              </ul>
            ) : null}
            <Space wrap align="start">
              <Space size="small" align="center">
                <GuardedButton
                  type="primary"
                  reason={blocked}
                  loading={pending === "agreement/accepted"}
                  onClick={() =>
                    confirmStep(
                      "agreement/accepted",
                      "Khách đã đồng ý",
                      accepting
                        ? "Ghi khách đã đồng ý xác nhận đơn, theo thư được đề xuất."
                        : "Ghi khách đã đồng ý xác nhận đơn (qua thư bạn đã đọc, điện thoại...).",
                      (key) =>
                        salesApi().recordAgreement(
                          order.case_id,
                          {
                            case_version: version,
                            how: "accepted",
                            message_id: accepting?.message_id ?? null,
                          },
                          key,
                        ),
                      "Đã ghi khách đồng ý",
                    )
                  }
                >
                  Khách đã đồng ý
                </GuardedButton>
                {accepting ? (
                  <StatusTag tone="warn">Đề xuất từ luồng thư</StatusTag>
                ) : null}
              </Space>
              <GuardedButton
                reason={impliedReason}
                loading={pending === "agreement/implied"}
                onClick={() =>
                  confirmStep(
                    "agreement/implied",
                    "Ghi đồng ý ngầm",
                    `Khách chưa trả lời quá ${sent.term ? termText(sent.term) : "số ngày"}. Ghi khách đồng ý ngầm?`,
                    (key) =>
                      salesApi().recordAgreement(
                        order.case_id,
                        { case_version: version, how: "implied" },
                        key,
                      ),
                    "Đã ghi khách đồng ý ngầm",
                  )
                }
              >
                Khách im lặng quá hạn → ghi đồng ý ngầm
              </GuardedButton>
              <Space size="small" align="center">
                <GuardedButton
                  danger
                  reason={blocked}
                  loading={pending === "agreement/declined"}
                  onClick={() =>
                    confirmStep(
                      "agreement/declined",
                      "Khách từ chối",
                      "Đơn chuyển sang xem thay đổi: sửa trên Bravo, kiểm chéo theo quy tắc, rồi gửi xác nhận lại.",
                      (key) =>
                        salesApi().recordDecline(order.case_id, version, key),
                      "Đã ghi khách từ chối",
                    )
                  }
                >
                  Khách từ chối
                </GuardedButton>
                {declining ? (
                  <StatusTag tone="warn">Đề xuất từ luồng thư</StatusTag>
                ) : null}
              </Space>
            </Space>
          </Space>
        ) : null}
        <ActionError error={error} />
      </Space>
    </Card>
  );
}
