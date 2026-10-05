"use client";

import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Radio,
  Space,
  theme,
  Typography,
} from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { FINDING_CODE, FINDING_DISPOSITION, label } from "../../_lib/labels";
import {
  dispositionOffer,
  isOpen,
  type Viewer,
} from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { FindingWords } from "../../_components/money";
import { DispositionTag, SeverityTag } from "../../_components/tags";

type Order = SalesSchemas["OrderCaseView"];
type Finding = SalesSchemas["OrderFindingView"];

/** The PRV-code findings are corrected by confirming the line's mapping. */
const MAPPING_CODES = ["code_unmapped", "code_ambiguous"];

/** The value a finding is about, to open its source on (a display choice). */
const FINDING_FIELD: Record<string, string> = {
  code_unmapped: "customer_item_code",
  code_ambiguous: "customer_item_code",
  price_mismatch: "unit_price",
  currency_mismatch: "unit_price",
  uom_mismatch: "uom",
  quotation_missing: "customer_item_code",
  lme_band_mismatch: "unit_price",
  moq_violation: "quantity",
  pack_multiple: "quantity",
  value_uncertain: "quantity",
  requested_date_short_lt: "requested_date",
  line_total_mismatch: "amount",
};

/** Exception-first: the open ones first, in the case's order otherwise. */
export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings.filter(isOpen), ...findings.filter((f) => !isOpen(f))];
}

/**
 * Per-finding decisions (G3, V3BidFindings re-cut): each finding offers only
 * the dispositions its code allows (`allowed`, from the API), one at a time,
 * with no "chấp nhận tất cả". After a decision the next open finding takes
 * focus, and the panel says how many remain.
 */
export function FindingsPanel({
  order,
  viewer,
  onChanged,
  onOpenSource,
  onPickCode,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
  onOpenSource: (field: string, lineNo: number | null) => void;
  onPickCode: (lineNo: number) => void;
}) {
  const findings = sortFindings(order.findings);
  const open = findings.filter(isOpen);
  const blocking = open.filter((f) => f.blocking).length;
  const refs = useRef(new Map<string, HTMLDivElement>());
  const [focusNext, setFocusNext] = useState(false);

  useEffect(() => {
    if (!focusNext) return;
    setFocusNext(false);
    const next = open[0];
    if (next) refs.current.get(next.key)?.focus();
  }, [focusNext, open]);

  return (
    <Card
      title="Cờ cần quyết định"
      size="small"
      extra={
        <span role="status">
          {open.length
            ? `Còn ${open.length} cờ chưa quyết định (${blocking} chặn)`
            : "Mọi cờ đã có quyết định"}
        </span>
      }
    >
      {findings.length === 0 ? (
        <Alert
          type="success"
          showIcon
          title="Không có cờ nào"
          description="Mọi kiểm tra trong phạm vi bên trên đã chạy và không có kết quả lệch. Vẫn cần mở nguồn trước khi chuẩn bị xong."
        />
      ) : (
        <div className="space-y-3">
          {findings.map((finding) => (
            <div
              key={finding.key}
              ref={(el) => {
                if (el) refs.current.set(finding.key, el);
              }}
              tabIndex={-1}
              aria-label={`${label(FINDING_CODE, finding.code)}${finding.line_no ? `, dòng ${finding.line_no}` : ""}`}
            >
              <FindingCard
                order={order}
                finding={finding}
                viewer={viewer}
                onDecided={() => {
                  onChanged();
                  setFocusNext(true);
                }}
                onOpenSource={onOpenSource}
                onPickCode={onPickCode}
              />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

type Choice = "accepted" | "corrected_by_sales" | "ask_customer";

function FindingCard({
  order,
  finding,
  viewer,
  onDecided,
  onOpenSource,
  onPickCode,
}: {
  order: Order;
  finding: Finding;
  viewer: Viewer;
  onDecided: () => void;
  onOpenSource: (field: string, lineNo: number | null) => void;
  onPickCode: (lineNo: number) => void;
}) {
  const name = usePeople();
  const { token } = theme.useToken();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const offer = dispositionOffer(order, finding, viewer);
  const choices = finding.allowed.filter((a): a is Choice => a !== "open");
  const [choice, setChoice] = useState<Choice | null>(null);
  const [form] = Form.useForm<{
    reason?: string;
    value?: string;
    source?: string;
  }>();
  const decided = !isOpen(finding);
  const mapping = MAPPING_CODES.includes(finding.code);
  const actionId = `finding/${finding.key}`;

  const send = async (
    disposition: Choice | "open",
    values: { reason?: string; value?: string; source?: string },
  ) => {
    const body = {
      case_version: order.case_version,
      disposition,
      reason: values.reason?.trim() || null,
      value: values.value?.trim() || null,
      source: values.source?.trim() || null,
    };
    const result = await run(
      `${actionId}/${disposition}`,
      body,
      (key) => salesApi().dispose(order.case_id, finding.key, body, key),
      disposition === "open"
        ? `Đã bỏ quyết định: ${label(FINDING_CODE, finding.code)}`
        : `Đã ghi: ${label(FINDING_DISPOSITION, disposition)}`,
    );
    if (result.ok) {
      setError(null);
      setChoice(null);
      form.resetFields();
      onDecided();
    } else setError(result.error);
  };

  const field = FINDING_FIELD[finding.code];
  // The prototype's findings row: a bar in the severity's colour while the
  // finding is open (the tags beside the title say it in words).
  const bar = decided
    ? token.colorBorderSecondary
    : finding.blocking
      ? token.colorError
      : token.colorWarning;
  return (
    <div
      className="rounded-lg border px-4 py-3"
      style={{
        background: token.colorBgContainer,
        borderInlineStartWidth: 4,
        borderInlineStartColor: bar,
      }}
    >
      <Space orientation="vertical" className="w-full" size="small">
        <Space wrap>
          <Typography.Text strong>
            {label(FINDING_CODE, finding.code)}
          </Typography.Text>
          <Typography.Text
            type="secondary"
            style={{ fontFamily: token.fontFamilyCode }}
          >
            {finding.line_no ? `dòng ${finding.line_no}` : "cả đơn"}
          </Typography.Text>
          <SeverityTag blocking={finding.blocking} />
          <DispositionTag kind={finding.disposition.kind} />
          {field && finding.line_no ? (
            <Button
              size="small"
              icon={<EyeOutlined aria-hidden />}
              onClick={() => onOpenSource(field, finding.line_no)}
            >
              Xem nguồn
            </Button>
          ) : null}
        </Space>
        <Typography.Text type="secondary">
          Mong đợi{" "}
          <Typography.Text>
            <FindingWords value={finding.expected} />
          </Typography.Text>{" "}
          · trên PO{" "}
          <Typography.Text>
            <FindingWords value={finding.actual} />
          </Typography.Text>
        </Typography.Text>
        {decided ? (
          <Typography.Text>
            {label(FINDING_DISPOSITION, finding.disposition.kind)}
            {finding.disposition.by ? ` · ${name(finding.disposition.by)}` : ""}
            {finding.disposition.at
              ? ` · ${formatDateTime(finding.disposition.at)}`
              : ""}
            {finding.disposition.reason
              ? ` · Lý do: ${finding.disposition.reason}`
              : ""}
            {typeof finding.disposition.value === "string"
              ? ` · Giá trị: ${finding.disposition.value}`
              : ""}
            {finding.disposition.source
              ? ` · Nguồn: ${finding.disposition.source}`
              : ""}
          </Typography.Text>
        ) : null}

        {offer === null ? null : offer.reason ? (
          <Typography.Text role="note">{offer.reason}</Typography.Text>
        ) : decided ? (
          <Button
            size="small"
            loading={pending === `${actionId}/open`}
            onClick={() => send("open", {})}
          >
            Bỏ quyết định
          </Button>
        ) : (
          <>
            <Radio.Group
              optionType="button"
              aria-label="Quyết định cho cờ này"
              value={choice}
              onChange={(event) => {
                const value = event.target.value as Choice;
                if (
                  mapping &&
                  value === "corrected_by_sales" &&
                  finding.line_no
                ) {
                  onPickCode(finding.line_no);
                  return;
                }
                setChoice(value);
              }}
              options={choices.map((c) => ({
                value: c,
                label:
                  c === "accepted"
                    ? "Chấp nhận + lý do"
                    : c === "corrected_by_sales"
                      ? mapping
                        ? "Chọn mã PRV"
                        : "Sửa giá trị"
                      : "Yêu cầu khách sửa",
              }))}
            />
            {choice ? (
              <Form
                form={form}
                layout="vertical"
                validateTrigger="onBlur"
                scrollToFirstError={{ focus: true }}
                onFinish={(values) => send(choice, values)}
              >
                {choice === "accepted" ? (
                  <Form.Item
                    name="reason"
                    label="Lý do chấp nhận"
                    rules={[
                      {
                        required: true,
                        message: "Lý do là bắt buộc",
                        validateTrigger: "onSubmit",
                      },
                    ]}
                  >
                    <Input.TextArea rows={2} maxLength={500} showCount />
                  </Form.Item>
                ) : null}
                {choice === "corrected_by_sales" ? (
                  <>
                    <Form.Item
                      name="value"
                      label="Giá trị đúng"
                      rules={[
                        {
                          required: true,
                          message: "Giá trị là bắt buộc",
                          validateTrigger: "onSubmit",
                        },
                      ]}
                    >
                      <Input maxLength={200} />
                    </Form.Item>
                    <Form.Item
                      name="source"
                      label="Lấy từ đâu"
                      extra="Ví dụ: thư khách xác nhận ngày 03/10, hoặc ô F12 của bản gốc."
                    >
                      <Input maxLength={500} />
                    </Form.Item>
                    <Typography.Paragraph>
                      Giá trị nhập tay ghi tên bạn; người kiểm chéo phải là
                      người khác.
                    </Typography.Paragraph>
                  </>
                ) : null}
                {choice === "ask_customer" ? (
                  <Typography.Paragraph>
                    Dòng này vào thư yêu cầu khách sửa PO. Đơn chờ bản sửa của
                    khách, bản sửa vào cùng hồ sơ.
                  </Typography.Paragraph>
                ) : null}
                <Space>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={pending === `${actionId}/${choice}`}
                  >
                    Ghi quyết định
                  </Button>
                  <Button onClick={() => setChoice(null)}>Hủy</Button>
                </Space>
              </Form>
            ) : null}
          </>
        )}
        <ActionError error={error} />
      </Space>
    </div>
  );
}
