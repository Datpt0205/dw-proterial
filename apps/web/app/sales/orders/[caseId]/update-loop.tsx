"use client";

import { useCallback, useState } from "react";
import { Alert, App, Card, Collapse, Space, Table, Typography } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { InfoTip, StatusTag } from "@dw/ui";
import { formatDate, formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import {
  ARTIFACT_KIND,
  INTERNAL_REASON,
  SUBFLOW_STEP,
  label,
} from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import type { CaseArtifacts } from "../../_components/artifacts-panel";
import { GuardedButton } from "../../_components/guarded-button";
import { Quantity } from "../../_components/money";
import { PcAnswerDialog } from "./pc-request";

type Order = SalesSchemas["OrderCaseView"];
type Loop = NonNullable<Order["update_loop"]>;
type LoopLine = Loop["lines"][number];
type Awaits = Loop["awaits"];
type Answer = "keep" | "accept" | "ask_pc_again";

const PREPARE = "sales.order.prepare";
const NO_SCOPE =
  "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách).";

/** The one step the loop waits on, in the BA's words (ticket 29). */
// The loop's own steps read the process map's words (one owner); the rest
// name what the Bravo-update step waits on in detail.
const AWAITS: Record<Awaits, string> = {
  ask_pc: SUBFLOW_STEP["update.ask_pc"],
  waiting_pc: SUBFLOW_STEP["update.waiting_pc"],
  answer_customer: SUBFLOW_STEP["update.answer_customer"],
  waiting_customer: SUBFLOW_STEP["update.waiting_customer"],
  approve_update: "Chờ duyệt tệp cập nhật Bravo",
  bravo_entry: "Chờ nhập Bravo",
  cross_check: "Chờ kiểm chéo",
  confirm: "Chờ xác nhận lại với khách",
};
const VERDICT = {
  can_do: "PC đáp ứng được như khách đề nghị",
  proposes: "PC đề xuất khác đề nghị của khách",
} as const;
/** The draft to the customer, by code's verdict (6-DW4 or 6-DW3). */
const ANSWER_DRAFT = {
  can_do: "change_can_do_draft",
  proposes: "change_options_draft",
} as const;

/**
 * A customer's change on an order already in Bravo (ticket 29, BA step 6):
 * the step it waits on and its one action, the changed lines held beside
 * asked with PC's answer, and the rest on click. DW1 sends nothing and
 * writes nothing to Bravo: each draft is copied and sent by a person, and
 * the Bravo update is the file the PIC approves. The server refuses every
 * step out of turn; a disabled button says why.
 */
export function UpdateLoopPanel({
  order,
  viewer,
  artifacts,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  artifacts: CaseArtifacts;
  onChanged: () => void;
}) {
  const loop = order.update_loop;
  if (!loop) return null;
  return (
    <LoopCard
      order={order}
      loop={loop}
      viewer={viewer}
      artifacts={artifacts}
      onChanged={onChanged}
    />
  );
}

function LoopCard({
  order,
  loop,
  viewer,
  artifacts,
  onChanged,
}: {
  order: Order;
  loop: Loop;
  viewer: Viewer;
  artifacts: CaseArtifacts;
  onChanged: () => void;
}) {
  const name = usePeople();
  const { message, modal } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [answering, setAnswering] = useState<LoopLine | null>(null);
  const may = viewer.hasScope(PREPARE);
  const asking = loop.step === "ask_pc" || loop.step === "waiting_pc";
  const draft = useResource(
    `sales/orders/${order.case_id}/update/pc-request@${order.case_version}`,
    useCallback(
      () => salesApi().updatePcRequest(order.case_id),
      [order.case_id],
    ),
    { enabled: may && asking },
  );
  const version = order.case_version;

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

  const request = order.change_requests.find(
    (r) => r.request_id === loop.request_id,
  );
  const undecided = request?.lines.some((x) => x.state === "open") ?? false;
  const askReason = !may
    ? NO_SCOPE
    : undecided
      ? "Còn dòng thay đổi chưa xác nhận hoặc từ chối: quyết định hết rồi hỏi PC."
      : null;

  const answer = (choice: Answer, title: string, content: string) =>
    modal.confirm({
      title,
      content,
      okText: title,
      cancelText: "Chưa ghi",
      autoFocusButton: "cancel",
      onOk: () =>
        step(
          `update/answer/${choice}`,
          (key) =>
            salesApi().recordUpdateCustomerAnswer(
              order.case_id,
              { case_version: version, answer: choice },
              key,
            ),
          "Đã ghi khách quyết định",
        ),
    });

  const update = artifacts.data?.artifacts.find(
    (a) => a.kind === "bravo_update" && a.case_version === version,
  );
  const openFindings = order.findings.some(
    (f) => f.disposition.kind === "open" && f.code !== "missing_noc_esf",
  );
  const approveReason = !may
    ? NO_SCOPE
    : openFindings
      ? "Còn cờ chưa quyết định trên đơn: quyết định hết rồi duyệt."
      : !update
        ? `Soạn “${label(ARTIFACT_KIND, "bravo_update")}” ở mục Tài liệu trước.`
        : null;

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã chép: dán vào Teams hoặc thư gửi PC");
    } catch {
      message.error("Trình duyệt không cho chép: chọn và chép tay nội dung.");
    }
  };

  const verdict = loop.verdict ? VERDICT[loop.verdict] : null;
  // Proterial's own change (ticket 10): PC's answer is in, nothing to ask.
  const internal = loop.reason ?? null;
  return (
    <Card
      size="small"
      title={
        internal
          ? `Thay đổi nội bộ: ${label(INTERNAL_REASON, internal)}`
          : "Khách xin thay đổi đơn đã nhập Bravo"
      }
    >
      <Space orientation="vertical" className="w-full">
        <Space wrap role="status">
          <StatusTag tone="warn">{AWAITS[loop.awaits]}</StatusTag>
          <Typography.Text>từ {formatDateTime(loop.since)}</Typography.Text>
          {verdict ? <StatusTag tone="pri">{verdict}</StatusTag> : null}
          {internal ? (
            <InfoTip label="Thay đổi nội bộ">
              PC đổi lịch sau xác nhận; đơn đã đổi theo các dòng bạn áp dụng.
              Soạn “{label(ARTIFACT_KIND, "internal_change_notice")}” ở mục Tài
              liệu và tự gửi khách. Duyệt đúng tệp cập nhật Bravo, nhập vào
              Bravo, đơn được kiểm chéo và xác nhận lại.
            </InfoTip>
          ) : (
            <InfoTip label="Vòng cập nhật">
              DW1 soạn bản hỏi PC và thư trả lời khách; bạn tự gửi rồi ghi lại.
              Đơn chỉ đổi khi khách đồng ý, sau đó bạn duyệt đúng tệp cập nhật
              Bravo, nhập vào Bravo, đơn được kiểm chéo và xác nhận lại.
            </InfoTip>
          )}
        </Space>

        {loop.awaits === "ask_pc" || loop.awaits === "waiting_pc" ? (
          <Space wrap>
            <GuardedButton
              icon={<CopyOutlined aria-hidden />}
              inlineReason={false}
              reason={
                !may
                  ? NO_SCOPE
                  : draft.data
                    ? null
                    : "Bản hỏi PC chưa tải được."
              }
              onClick={() =>
                draft.data
                  ? void copy(`${draft.data.subject}\n\n${draft.data.body}`)
                  : null
              }
            >
              Chép bản hỏi PC
            </GuardedButton>
            <GuardedButton
              type={loop.awaits === "ask_pc" ? "primary" : "default"}
              reason={askReason}
              loading={pending === "update/asked"}
              onClick={() =>
                void step(
                  "update/asked",
                  (key) =>
                    salesApi().recordUpdatePcAsked(order.case_id, version, key),
                  "Đã ghi đã hỏi PC",
                )
              }
            >
              Ghi đã hỏi PC
            </GuardedButton>
            {loop.awaits === "waiting_pc" && draft.data ? (
              <Typography.Text>
                {draft.data.reminder_at
                  ? `DW1 nhắc lúc ${formatDateTime(draft.data.reminder_at)} nếu PC chưa trả lời`
                  : "Nhắc chờ PC đang tắt trong quy tắc"}
              </Typography.Text>
            ) : null}
          </Space>
        ) : null}

        {loop.awaits === "answer_customer" && loop.verdict ? (
          <Space wrap>
            <Typography.Text>
              Soạn “{label(ARTIFACT_KIND, ANSWER_DRAFT[loop.verdict])}” ở mục
              Tài liệu, gửi từ hộp thư của bạn, rồi ghi lại.
            </Typography.Text>
            <GuardedButton
              type="primary"
              reason={may ? null : NO_SCOPE}
              loading={pending === "update/sent"}
              onClick={() =>
                void step(
                  "update/sent",
                  (key) =>
                    salesApi().recordUpdateAnswerSent(
                      order.case_id,
                      version,
                      key,
                    ),
                  "Đã ghi đã gửi khách",
                )
              }
            >
              Ghi đã gửi khách
            </GuardedButton>
          </Space>
        ) : null}

        {loop.awaits === "waiting_customer" ? (
          <Space wrap>
            <GuardedButton
              type="primary"
              reason={may ? null : NO_SCOPE}
              loading={pending === "update/answer/accept"}
              onClick={() =>
                answer(
                  "accept",
                  "Khách đồng ý",
                  "Thay đổi được áp vào đơn và đơn chuyển sang cập nhật Bravo: duyệt tệp, nhập Bravo, kiểm chéo và xác nhận lại.",
                )
              }
            >
              Khách đồng ý
            </GuardedButton>
            <GuardedButton
              reason={may ? null : NO_SCOPE}
              loading={pending === "update/answer/keep"}
              onClick={() =>
                answer(
                  "keep",
                  "Khách giữ PO cũ",
                  `Vòng cập nhật kết thúc, PO ${order.po_no} giữ nguyên như đã xác nhận.`,
                )
              }
            >
              Khách giữ PO cũ
            </GuardedButton>
            <GuardedButton
              reason={may ? null : NO_SCOPE}
              loading={pending === "update/answer/ask_pc_again"}
              onClick={() =>
                answer(
                  "ask_pc_again",
                  "Hỏi PC lại",
                  "Câu trả lời của PC được bỏ; hỏi PC lần nữa.",
                )
              }
            >
              Hỏi PC lại
            </GuardedButton>
          </Space>
        ) : null}

        {loop.awaits === "approve_update" ? (
          <Space wrap>
            {update ? (
              <Typography.Text>
                Tệp phiên bản {update.case_version} · mã băm{" "}
                <Typography.Text code>
                  {update.sha256.slice(0, 12)}
                </Typography.Text>
              </Typography.Text>
            ) : null}
            <GuardedButton
              type="primary"
              reason={approveReason}
              loading={pending === "update/approve"}
              onClick={() =>
                update
                  ? void step(
                      "update/approve",
                      (key) =>
                        salesApi().approveBravoUpdate(
                          order.case_id,
                          {
                            case_version: version,
                            artifact_id: update.artifact_id,
                          },
                          key,
                        ),
                      "Đã duyệt tệp cập nhật Bravo",
                    )
                  : null
              }
            >
              Duyệt tệp cập nhật Bravo
            </GuardedButton>
          </Space>
        ) : null}

        {loop.approval ? (
          <Typography.Text>
            {name(loop.approval.by)} đã duyệt tệp cập nhật Bravo lúc{" "}
            {formatDateTime(loop.approval.at)} (mã băm{" "}
            <Typography.Text code>
              {loop.approval.sha256.slice(0, 12)}
            </Typography.Text>
            )
            {loop.awaits === "bravo_entry"
              ? ": nhập tệp này vào Bravo rồi ghi đã nhập ở mục thao tác."
              : "."}
          </Typography.Text>
        ) : null}

        <ActionError error={error} />

        <Table<LoopLine>
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={loop.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no", width: 64 },
            {
              title: internal ? "Cắt số lượng" : "Đơn đang giữ → khách xin",
              key: "asked",
              render: (_, l) => (
                <Space orientation="vertical" size={0}>
                  {l.asked_requested_date ? (
                    <Typography.Text>
                      Ngày:{" "}
                      {l.held_requested_date
                        ? formatDate(l.held_requested_date)
                        : "Báo sau"}{" "}
                      → {formatDate(l.asked_requested_date)}
                    </Typography.Text>
                  ) : null}
                  {l.asked_quantity && internal ? (
                    <Typography.Text>
                      Còn <Quantity value={l.asked_quantity} />
                    </Typography.Text>
                  ) : l.asked_quantity ? (
                    <Typography.Text>
                      Số lượng: <Quantity value={l.held_quantity} /> →{" "}
                      <Quantity value={l.asked_quantity} />
                    </Typography.Text>
                  ) : null}
                </Space>
              ),
            },
            {
              title: "PC trả lời",
              key: "pc",
              render: (_, l) =>
                l.pc_deliveries ? (
                  <Space orientation="vertical" size={0}>
                    {l.pc_deliveries.map((d, index) => (
                      <Typography.Text key={index}>
                        <Quantity value={d.quantity} /> · {formatDate(d.date)}
                      </Typography.Text>
                    ))}
                  </Space>
                ) : (
                  <Typography.Text>Chưa có</Typography.Text>
                ),
            },
            {
              title: "",
              key: "action",
              fixed: "right",
              // PC's own change carries PC's answer already.
              hidden: internal !== null,
              render: (_, l) => (
                <GuardedButton
                  size="small"
                  inlineReason={false}
                  reason={
                    !may
                      ? NO_SCOPE
                      : loop.step === "waiting_pc"
                        ? null
                        : "Ghi ngày PC sau khi đã ghi hỏi PC, trước khi gửi khách."
                  }
                  onClick={() => setAnswering(l)}
                  aria-label={`Ghi ngày PC trả lời cho dòng ${l.line_no}`}
                >
                  Ghi ngày PC
                </GuardedButton>
              ),
            },
          ]}
        />

        {asking && draft.data ? (
          <Collapse
            size="small"
            items={[
              {
                key: "draft",
                label: "Xem bản hỏi PC",
                children: (
                  <Alert
                    type="info"
                    title={draft.data.subject}
                    description={
                      <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
                        {draft.data.body}
                      </Typography.Paragraph>
                    }
                  />
                ),
              },
            ]}
          />
        ) : null}
      </Space>
      {answering ? (
        <PcAnswerDialog
          order={order}
          lineNo={answering.line_no}
          quantity={answering.asked_quantity ?? answering.held_quantity}
          uom={
            order.lines.find((x) => x.line_no === answering.line_no)?.uom ?? ""
          }
          initial={
            answering.pc_deliveries ?? [
              {
                quantity: answering.asked_quantity ?? answering.held_quantity,
                date:
                  answering.asked_requested_date ??
                  answering.held_requested_date,
              },
            ]
          }
          send={(body, key) =>
            salesApi().recordUpdatePcAnswer(
              order.case_id,
              answering.line_no,
              body,
              key,
            )
          }
          onClose={() => setAnswering(null)}
          onDone={() => {
            setAnswering(null);
            onChanged();
          }}
        />
      ) : null}
    </Card>
  );
}
