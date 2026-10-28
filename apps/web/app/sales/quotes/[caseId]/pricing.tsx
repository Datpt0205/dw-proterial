"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Segmented,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { formatDateTime, formatMonth } from "../../../../lib/dates";
import { errorCode } from "../../../../lib/error-message";
import {
  formatMoney,
  formatQuantity,
  type Currency,
} from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError, refusalSentences } from "../../_lib/errors";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { AmountInput } from "../../_components/amount-input";
import { isHidden, Money, Quantity } from "../../_components/money";

type Quote = SalesSchemas["QuoteCaseView"];
type Suggestion = SalesSchemas["SuggestionView"];

/** DW1's suggested price per line, from the evidence the caller may see. */
function suggestions(quote: Quote): Map<number, Suggestion> {
  const evidence = quote.evidence;
  if (!evidence || isHidden(evidence)) return new Map();
  return new Map(
    evidence.flatMap((line) =>
      line.suggestion ? [[line.line_no, line.suggestion] as const] : [],
    ),
  );
}

/** "đơn SO25-1120 gần nhất của khách, nâng lên giá sàn" */
function basisText(suggestion: Suggestion): string {
  const basis =
    suggestion.basis === "own_quotation"
      ? `báo giá ${suggestion.source_no} còn hiệu lực của khách`
      : suggestion.basis === "last_order"
        ? `đơn ${suggestion.source_no} gần nhất của khách`
        : "giá tham chiếu nội bộ";
  return suggestion.raised_to_floor ? `${basis}, nâng lên giá sàn` : basis;
}

interface LineValues {
  unit_price: string;
  moq: string;
  lead_time_days: string;
  copper: "fixed" | "lme_band";
  low?: string;
  high?: string;
}

interface Values {
  lme_month?: string;
  management_guidance?: string;
  lines: Record<string, LineValues>;
}

function initial(quote: Quote): Values {
  const decided = new Map(
    (quote.pricing?.lines ?? []).map((l) => [l.line_no, l]),
  );
  const text = (value: unknown) => (typeof value === "string" ? value : "");
  return {
    lme_month: quote.pricing?.lme?.month,
    management_guidance:
      typeof quote.pricing?.management_guidance === "string"
        ? quote.pricing.management_guidance
        : undefined,
    lines: Object.fromEntries(
      quote.lines.map((line) => {
        const d = decided.get(line.line_no);
        return [
          `l${line.line_no}`,
          {
            unit_price: text(d?.unit_price),
            moq: d ? d.moq : "",
            lead_time_days: d ? String(d.lead_time_days) : "",
            copper: d?.copper_basis.kind ?? "fixed",
            low: text(d?.copper_basis.low_usd_per_tonne),
            high: text(d?.copper_basis.high_usd_per_tonne),
          },
        ];
      }),
    ),
  };
}

/** Refused because someone saved the case first (`stale_case_version`). */
function isStaleVersion(error: unknown): boolean {
  return (
    errorCode(error) === "conflict" &&
    error instanceof ApiError &&
    error.body.details?.rule === "stale_case_version"
  );
}

/**
 * Sales decides the price (Q7): per line the unit price, MOQ, lead time and
 * how the price follows copper, against the LME month master data holds.
 * DW1's suggestion for each line, with the row it came from, sits beside the
 * price and fills only the empty fields when asked: a starting point, never
 * recorded on its own (2026-10-28, "Sales nhập giá; DW1 chỉ đưa căn cứ"). The
 * figures are read on the server again (the LME value from the month named,
 * never from here), the decision is stamped with the caller as its pricer,
 * and the quotation findings are raised from it. Changing a price after
 * submitting withdraws the document the approver was shown.
 */
export function PricingForm({
  quote,
  onDone,
}: {
  quote: Quote;
  onDone: () => void;
}) {
  const [form] = Form.useForm<Values>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(0);
  // The case as saved by whoever recorded first, read after a refusal for a
  // stale version (ui-quality §4 "conflict"): shown beside what this person
  // typed, which the form keeps, until they choose which price stands.
  const [theirs, setTheirs] = useState<Quote | null>(null);
  const typedLines = Form.useWatch("lines", form);
  const lme = useResource(
    "sales/master-data/lme",
    useCallback(() => salesApi().lme(), []),
  );
  const currency = quote.currency as Currency;
  // The latest published LME month is what the policy prices against: filled
  // in when nothing was decided yet, changeable by Sales.
  const latest = lme.data?.items.at(-1)?.month;
  useEffect(() => {
    if (latest && !form.getFieldValue("lme_month"))
      form.setFieldValue("lme_month", latest);
  }, [latest, form]);
  const resubmit = ["pending_approval", "approved"].includes(quote.status);
  const suggested = suggestions(quote);

  /** "Điền giá DW1 gợi ý": only into the fields still empty; Sales records. */
  const fillSuggested = () => {
    const lines = form.getFieldValue("lines") as Values["lines"];
    for (const [lineNo, suggestion] of suggested) {
      const key = `l${lineNo}`;
      const typed = lines[key];
      const fill: Partial<LineValues> = {};
      if (!typed?.unit_price) fill.unit_price = suggestion.unit_price;
      if (!typed?.moq && suggestion.moq) fill.moq = suggestion.moq;
      if (!typed?.lead_time_days && suggestion.lead_time_days)
        fill.lead_time_days = String(suggestion.lead_time_days);
      const copper = suggestion.copper_basis;
      const [low, high] = [
        copper?.low_usd_per_tonne,
        copper?.high_usd_per_tonne,
      ];
      if (
        typeof low === "string" &&
        typeof high === "string" &&
        !typed?.low &&
        !typed?.high
      ) {
        fill.copper = "lme_band";
        fill.low = low;
        fill.high = high;
      }
      form.setFieldValue(["lines", key], { ...typed, ...fill });
    }
  };

  const submit = async (values: Values) => {
    setFailed(0);
    const body = {
      // After a conflict, "Dùng giá của tôi" records on the version now saved.
      case_version: theirs?.case_version ?? quote.case_version,
      lme_month: values.lme_month ?? null,
      management_guidance: values.management_guidance?.trim() || null,
      lines: quote.lines.map((line) => {
        const v = values.lines[`l${line.line_no}`]!;
        return {
          line_no: line.line_no,
          unit_price: v.unit_price,
          moq: v.moq,
          lead_time_days: Number(v.lead_time_days),
          copper_basis:
            v.copper === "fixed"
              ? { kind: "fixed" as const }
              : {
                  kind: "lme_band" as const,
                  low_usd_per_tonne: v.low ?? "",
                  high_usd_per_tonne: v.high ?? "",
                },
        };
      }),
    };
    const result = await run(
      "price",
      body,
      (key) => salesApi().price(quote.case_id, body, key),
      "Đã ghi giá: các cờ báo giá đã được tính lại",
    );
    if (result.ok) {
      setError(null);
      setTheirs(null);
      onDone();
      return;
    }
    setError(result.error);
    if (!isStaleVersion(result.error)) return;
    try {
      setTheirs(await salesApi().quote(quote.case_id));
    } catch {
      // Unreadable now: the refusal itself is still drawn, the typed values kept.
      setTheirs(null);
    }
  };

  /** "Giữ giá hiện có": take the saved price into the form, drop what was typed. */
  const keepSaved = (saved: Quote) => {
    form.setFieldsValue(initial(saved));
    setTheirs(null);
    setError(null);
    onDone();
  };

  const required = (message: string) => [
    { required: true, message, validateTrigger: "onSubmit" },
  ];

  return (
    <Card size="small" title="Quyết định giá">
      {resubmit ? (
        <Alert
          className="mb-3"
          type="warning"
          showIcon
          title="Đổi giá sau khi trình sẽ rút tài liệu người duyệt đang xem; báo giá phải trình duyệt lại."
        />
      ) : null}
      {failed ? (
        <Alert
          className="mb-3"
          type="error"
          showIcon
          title={`Còn ${failed} trường cần sửa.`}
        />
      ) : null}
      <Form<Values>
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        scrollToFirstError={{ focus: true }}
        initialValues={initial(quote)}
        onFinishFailed={({ errorFields }) => setFailed(errorFields.length)}
        onFinish={submit}
      >
        <Table
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={quote.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Yêu cầu",
              key: "req",
              render: (_, line) => (
                <Space orientation="vertical" size={0} className="max-w-60">
                  <Typography.Text ellipsis={{ tooltip: line.description }}>
                    {line.description}
                  </Typography.Text>
                  <Quantity value={line.quantity} uom={line.uom} />
                </Space>
              ),
            },
            {
              title: `Đơn giá (${currency})`,
              key: "price",
              render: (_, line) => (
                <Form.Item
                  name={["lines", `l${line.line_no}`, "unit_price"]}
                  className="!mb-0 min-w-44"
                  rules={[
                    ...required("Đơn giá là bắt buộc"),
                    {
                      validator: (_, v) =>
                        !v || Number(v) > 0
                          ? Promise.resolve()
                          : Promise.reject(new Error("Đơn giá phải lớn hơn 0")),
                    },
                  ]}
                >
                  <AmountInput
                    currency={currency}
                    aria-label={`Đơn giá dòng ${line.line_no}`}
                  />
                </Form.Item>
              ),
            },
            {
              title: "DW1 gợi ý",
              key: "suggested",
              render: (_, line) => {
                const suggestion = suggested.get(line.line_no);
                return suggestion ? (
                  <Space orientation="vertical" size={0} className="max-w-56">
                    <Money value={suggestion.unit_price} currency={currency} />
                    <Typography.Text type="secondary">
                      {basisText(suggestion)}
                    </Typography.Text>
                  </Space>
                ) : (
                  <Typography.Text type="secondary">
                    Chưa có căn cứ để gợi ý
                  </Typography.Text>
                );
              },
            },
            {
              title: "MOQ",
              key: "moq",
              render: (_, line) => (
                <Form.Item
                  name={["lines", `l${line.line_no}`, "moq"]}
                  className="!mb-0 min-w-28"
                  rules={[
                    ...required("MOQ là bắt buộc"),
                    {
                      validator: (_, v) =>
                        !v || Number(v) > 0
                          ? Promise.resolve()
                          : Promise.reject(new Error("MOQ phải lớn hơn 0")),
                    },
                  ]}
                >
                  <AmountInput aria-label={`MOQ dòng ${line.line_no}`} />
                </Form.Item>
              ),
            },
            {
              title: "Lead time (ngày)",
              key: "lt",
              render: (_, line) => (
                <Form.Item
                  name={["lines", `l${line.line_no}`, "lead_time_days"]}
                  className="!mb-0 min-w-24"
                  rules={[
                    ...required("Lead time là bắt buộc"),
                    {
                      validator: (_, v) =>
                        !v ||
                        /^([1-9]\d?|[12]\d\d|3[0-5]\d|36[0-5])$/.test(String(v))
                          ? Promise.resolve()
                          : Promise.reject(
                              new Error(
                                "Lead time là số ngày nguyên từ 1 đến 365",
                              ),
                            ),
                    },
                  ]}
                >
                  <AmountInput aria-label={`Lead time dòng ${line.line_no}`} />
                </Form.Item>
              ),
            },
            {
              title: "Căn cứ đồng",
              key: "cu",
              render: (_, line) => (
                <Space orientation="vertical" size={4}>
                  <Form.Item
                    name={["lines", `l${line.line_no}`, "copper"]}
                    className="!mb-0"
                  >
                    <Segmented
                      aria-label={`Căn cứ đồng dòng ${line.line_no}`}
                      options={[
                        { value: "fixed", label: "Cố định" },
                        { value: "lme_band", label: "Theo dải LME" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item noStyle shouldUpdate>
                    {() =>
                      form.getFieldValue([
                        "lines",
                        `l${line.line_no}`,
                        "copper",
                      ]) === "lme_band" ? (
                        <Space>
                          <Form.Item
                            name={["lines", `l${line.line_no}`, "low"]}
                            className="!mb-0"
                            rules={required("Cần mức dưới")}
                          >
                            <AmountInput
                              currency="USD"
                              placeholder="Từ"
                              aria-label={`LME từ (USD/tấn) dòng ${line.line_no}`}
                            />
                          </Form.Item>
                          <Form.Item
                            name={["lines", `l${line.line_no}`, "high"]}
                            className="!mb-0"
                            rules={required("Cần mức trên")}
                          >
                            <AmountInput
                              currency="USD"
                              placeholder="Đến"
                              aria-label={`LME đến (USD/tấn) dòng ${line.line_no}`}
                            />
                          </Form.Item>
                        </Space>
                      ) : null
                    }
                  </Form.Item>
                </Space>
              ),
            },
          ]}
        />
        <Space wrap className="mt-3" align="start">
          <Form.Item
            name="lme_month"
            label="Tháng LME làm căn cứ"
            className="min-w-56"
          >
            <Select
              allowClear
              showSearch={{ optionFilterProp: "label" }}
              loading={lme.loading}
              options={(lme.data?.items ?? []).map((m) => ({
                value: m.month,
                label: `Tháng ${formatMonth(m.month)}`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="management_guidance"
            label="Ghi chú chỉ đạo"
            className="min-w-80"
          >
            <Input.TextArea rows={2} maxLength={2000} showCount />
          </Form.Item>
        </Space>
        <Space wrap>
          <Button
            type="primary"
            htmlType="submit"
            loading={pending === "price"}
          >
            {quote.pricing ? "Ghi giá mới" : "Ghi giá"}
          </Button>
          {suggested.size ? (
            <Button onClick={fillSuggested}>Điền giá DW1 gợi ý</Button>
          ) : null}
        </Space>
        {suggested.size ? (
          <Typography.Paragraph type="secondary" className="!mt-2 !mb-0">
            Giá gợi ý chỉ điền vào ô còn trống; bạn sửa tuỳ ý và giá được ghi là
            quyết định của bạn.
          </Typography.Paragraph>
        ) : null}
      </Form>
      <div className="mt-3">
        {theirs ? (
          <PricingConflict
            error={error}
            saved={theirs}
            currency={currency}
            pending={pending === "price"}
            onMine={() => form.submit()}
            onKeep={() => keepSaved(theirs)}
            typed={(lineNo) => typedLines?.[`l${lineNo}`]}
          />
        ) : (
          <ActionError error={error} />
        )}
      </div>
    </Card>
  );
}

/** "0,74 USD · MOQ 3.000 · 45 ngày", or what is still missing. */
function lineTerms(
  price: string | null,
  moq: string,
  leadTime: string,
  currency: Currency,
): string {
  return [
    price ? formatMoney(price, currency) : "chưa nhập đơn giá",
    moq ? `MOQ ${formatQuantity(moq)}` : null,
    leadTime ? `${leadTime} ngày` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

/**
 * Someone recorded first (ui-quality §4 "conflict"): the price now saved, by
 * whom and when, beside what this person typed (kept in the form), and the
 * two ways on. Never a silent overwrite: "Dùng giá của tôi" records again on
 * the saved version, knowingly; "Giữ giá hiện có" takes the saved price.
 */
function PricingConflict({
  error,
  saved,
  currency,
  pending,
  onMine,
  onKeep,
  typed,
}: {
  error: unknown;
  saved: Quote;
  currency: Currency;
  pending: boolean;
  onMine: () => void;
  onKeep: () => void;
  typed: (lineNo: number) => LineValues | undefined;
}) {
  const name = usePeople();
  const pricing = saved.pricing;
  const savedLines = new Map((pricing?.lines ?? []).map((l) => [l.line_no, l]));
  return (
    <Alert
      type="warning"
      showIcon
      role="alert"
      title={
        pricing
          ? `Người khác vừa ghi giá: ${name(pricing.decided_by)} lúc ${formatDateTime(pricing.decided_at)}`
          : "Người khác vừa thay đổi hồ sơ này"
      }
      description={
        <Space orientation="vertical" size={4} className="w-full">
          <Typography.Text>{refusalSentences(error)[0]}</Typography.Text>
          <ul className="m-0 list-none p-0">
            {saved.lines.map((line) => {
              const mine = typed(line.line_no);
              const theirsLine = savedLines.get(line.line_no);
              return (
                <li key={line.line_no}>
                  <Typography.Text strong>Dòng {line.line_no}</Typography.Text>
                  {" · đang lưu: "}
                  {theirsLine ? (
                    <>
                      <Money
                        value={theirsLine.unit_price}
                        currency={currency}
                      />
                      {` · MOQ ${formatQuantity(theirsLine.moq)} · ${theirsLine.lead_time_days} ngày`}
                    </>
                  ) : (
                    "chưa có giá"
                  )}
                  {" · bạn đang nhập: "}
                  {lineTerms(
                    mine?.unit_price || null,
                    mine?.moq ?? "",
                    mine?.lead_time_days ?? "",
                    currency,
                  )}
                </li>
              );
            })}
          </ul>
          <Typography.Text>
            Giá bạn nhập vẫn giữ trong các ô bên trên. Chọn giá nào được ghi:
          </Typography.Text>
          <Space wrap>
            <Button loading={pending} onClick={onMine}>
              Dùng giá của tôi
            </Button>
            <Button disabled={pending} onClick={onKeep}>
              Giữ giá hiện có
            </Button>
          </Space>
        </Space>
      }
    />
  );
}
