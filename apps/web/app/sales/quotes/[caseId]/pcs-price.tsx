"use client";

import { useState } from "react";
import {
  Alert,
  Button,
  Form,
  Modal,
  Segmented,
  Space,
  Table,
  Tooltip,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime } from "../../../../lib/dates";
import type { Currency } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useSalesViewer } from "../../_lib/viewer";
import { AmountInput } from "../../_components/amount-input";
import { Money, Quantity } from "../../_components/money";

type Quote = SalesSchemas["QuoteCaseView"];
type Sheet = SalesSchemas["PcsCostSheet"];
type Kind = "mass" | "pcs";

// Mass or pcs is set before the case is priced and sent, as
// `QuoteCase.set_production_type` decides; the server refuses otherwise.
const CLOSED = new Set(["sent", "master_list_recorded", "declined"]);

/**
 * Ticket 05: mass or pcs, and for pcs the GM/BC Manager's price, which
 * Sales records before pricing the case. The server refuses a pcs case's
 * price without it; this panel says so first.
 */
export function PcsPricePanel({
  quote,
  onDone,
}: {
  quote: Quote;
  onDone: () => void;
}) {
  const viewer = useSalesViewer();
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [sheetError, setSheetError] = useState<unknown>(null);
  const [form] = Form.useForm<Record<string, string>>();
  const currency = quote.currency as Currency;
  const canPrepare = viewer.hasScope("sales.quote.prepare");
  const settable = !CLOSED.has(quote.status) && quote.pricing == null;
  const blocked = !canPrepare
    ? "Cần quyền chuẩn bị báo giá"
    : !settable
      ? "Chỉ chọn được trước khi định giá"
      : null;

  const setKind = async (kind: Kind) => {
    const body = { case_version: quote.case_version, kind };
    const result = await run(
      "production_type",
      body,
      (key) => salesApi().productionType(quote.case_id, body, key),
      kind === "pcs" ? "Đã đánh dấu hàng pcs" : "Đã đánh dấu hàng mass",
    );
    setError(result.ok ? null : result.error);
    if (result.ok) onDone();
  };

  const record = async (values: Record<string, string>) => {
    const body = {
      case_version: quote.case_version,
      lines: quote.lines.map((line) => ({
        line_no: line.line_no,
        unit_price: values[String(line.line_no)] ?? "",
      })),
    };
    const result = await run(
      "pcs_price",
      body,
      (key) => salesApi().pcsPrice(quote.case_id, body, key),
      "Đã ghi giá GM",
    );
    setError(result.ok ? null : result.error);
    if (result.ok) onDone();
  };

  const openSheet = async () => {
    try {
      setSheet(await salesApi().pcsPriceRequest(quote.case_id));
      setSheetError(null);
    } catch (e) {
      setSheetError(e);
    }
  };

  return (
    <Space orientation="vertical" className="w-full">
      <Space wrap>
        <Typography.Text>Loại hàng</Typography.Text>
        <Tooltip title={blocked}>
          <Segmented<Kind>
            aria-label="Loại hàng"
            value={(quote.production_type as Kind | null) ?? undefined}
            disabled={blocked !== null || pending !== null}
            options={[
              { label: "Mass", value: "mass" },
              { label: "Pcs", value: "pcs" },
            ]}
            onChange={(kind) => void setKind(kind)}
          />
        </Tooltip>
        {quote.production_type_set ? (
          <Typography.Text>
            {name(quote.production_type_set.by)} ·{" "}
            {formatDateTime(quote.production_type_set.at)}
          </Typography.Text>
        ) : (
          <Typography.Text>Chưa chọn</Typography.Text>
        )}
      </Space>

      {quote.production_type === "pcs" ? (
        <>
          {quote.waits_on_pcs_price ? (
            <Alert
              type="warning"
              showIcon
              message="Hàng pcs: cần giá GM/BC Manager đã chốt trước khi định giá"
            />
          ) : null}
          <Button onClick={() => void openSheet()}>Xem bảng hỏi giá GM</Button>
          {sheetError ? <ActionError error={sheetError} /> : null}

          {quote.pcs_price ? (
            <Table
              size="small"
              rowKey="line_no"
              pagination={false}
              dataSource={quote.pcs_price.lines}
              title={() =>
                `Giá GM do ${name(quote.pcs_price!.recorded_by)} ghi · ${formatDateTime(quote.pcs_price!.recorded_at)}`
              }
              columns={[
                { title: "Dòng", dataIndex: "line_no" },
                {
                  title: `Đơn giá GM (${currency})`,
                  align: "right",
                  render: (_, line) => (
                    <Money value={line.unit_price} currency={currency} />
                  ),
                },
              ]}
            />
          ) : null}

          {canPrepare && settable ? (
            <Form form={form} layout="inline" onFinish={(v) => void record(v)}>
              {quote.lines.map((line) => (
                <Form.Item
                  key={line.line_no}
                  name={String(line.line_no)}
                  label={`Giá GM dòng ${line.line_no}`}
                  rules={[
                    {
                      required: true,
                      message: "Cần đơn giá",
                      validateTrigger: "onSubmit",
                    },
                  ]}
                >
                  <AmountInput currency={currency} />
                </Form.Item>
              ))}
              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={pending === "pcs_price"}
                >
                  Ghi giá GM
                </Button>
              </Form.Item>
            </Form>
          ) : null}
        </>
      ) : null}
      {error ? <ActionError error={error} /> : null}

      <Modal
        open={sheet !== null}
        title="Bảng hỏi giá GM/BC Manager"
        footer={null}
        onCancel={() => setSheet(null)}
        width={720}
      >
        {sheet ? (
          <Space orientation="vertical" className="w-full">
            <Typography.Text>
              {sheet.customer_code}
              {sheet.rfq_no ? ` · ${sheet.rfq_no}` : ""}
            </Typography.Text>
            <Table
              size="small"
              rowKey="line_no"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={sheet.rows}
              columns={[
                { title: "Dòng", dataIndex: "line_no" },
                { title: "Mã khách", dataIndex: "customer_item_code" },
                { title: "Mô tả", dataIndex: "description" },
                {
                  title: "Số lượng",
                  align: "right",
                  render: (_, row) => (
                    <Quantity value={row.quantity} uom={row.uom} />
                  ),
                },
                { title: "Đơn giá", render: () => "" },
              ]}
            />
            <Typography.Text>Các dòng chi phí GM điền:</Typography.Text>
            <ul>
              {sheet.cost_lines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </Space>
        ) : null}
      </Modal>
    </Space>
  );
}
