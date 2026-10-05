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
import type { SalesSchemas } from "@dw/api-client";
import { formatMonth } from "../../../../lib/dates";
import type { Currency } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { AmountInput } from "../../_components/amount-input";
import { Quantity } from "../../_components/money";

type Quote = SalesSchemas["QuoteCaseView"];

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

/**
 * Sales decides the price (Q7): per line the unit price, MOQ, lead time and
 * how the price follows copper, against the LME month master data holds. The
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

  const submit = async (values: Values) => {
    setFailed(0);
    const body = {
      case_version: quote.case_version,
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
      onDone();
    } else setError(result.error);
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
        <Space>
          <Button
            type="primary"
            htmlType="submit"
            loading={pending === "price"}
          >
            {quote.pricing ? "Ghi giá mới" : "Ghi giá"}
          </Button>
        </Space>
      </Form>
      <div className="mt-3">
        <ActionError error={error} />
      </div>
    </Card>
  );
}
