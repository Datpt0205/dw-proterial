"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Radio,
  Space,
  Table,
  Typography,
} from "antd";
import { StatusTag } from "@dw/ui";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState } from "../../../../components/region-state";
import { formatQuantity } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { label, MAPPING_STATUS } from "../../_lib/labels";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";

type Order = SalesSchemas["OrderCaseView"];
type Line = SalesSchemas["OrderLineView"];
type Item = SalesSchemas["ItemView"];

const PRV_CODE = /^[A-Z0-9][A-Z0-9-]{1,31}$/;

interface Row {
  key: string;
  attribute: string;
  po: string;
  /** Per candidate: the item's value and whether it fits the PO (null: no verdict). */
  values: Record<string, { text: string; fits: boolean | null }>;
}

function fit(fits: boolean | null) {
  if (fits === null) return null;
  return fits ? (
    <StatusTag tone="ok" icon={<CheckCircleOutlined aria-hidden />}>
      khớp
    </StatusTag>
  ) : (
    <StatusTag tone="err" icon={<CloseCircleOutlined aria-hidden />}>
      lệch
    </StatusTag>
  );
}

/**
 * The candidate picker (G13): the PO line beside each candidate item, one
 * attribute per row, PO value | item value | khớp/lệch. Only the attributes the
 * PO states as its own fields are compared here (unit, quantity against MOQ
 * and pack); the cable attributes stay in the PO's description, shown above,
 * because the API does not send what DW1 read from it, and a second reader in
 * the browser would be a second answer. DW1 checks the line again against the
 * code Sales confirms, and any finding it raises lands on the case.
 */
export function CandidatePicker({
  order,
  lineNo,
  onClose,
  onDone,
  onOpenSource,
}: {
  order: Order;
  lineNo: number | null;
  onClose: () => void;
  onDone: () => void;
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  const line = order.lines.find((l) => l.line_no === lineNo) ?? null;
  const items = useResource(
    "sales/master-data/items",
    useCallback(() => salesApi().items(), []),
    { enabled: line !== null },
  );
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  useEffect(() => {
    setPicked(null);
    setTyped("");
    setError(null);
  }, [lineNo]);

  if (!line) return null;
  const candidates = line.mapping.candidates;
  const typing = candidates.length === 0;
  const code = typing ? typed.trim() : picked;
  const byCode = new Map((items.data?.items ?? []).map((i) => [i.prv_code, i]));
  const shown: string[] = typing
    ? code && PRV_CODE.test(code)
      ? [code]
      : []
    : candidates;

  const confirm = async () => {
    if (!code) return;
    const body = { case_version: order.case_version, prv_code: code };
    const result = await run(
      `mapping/${line.line_no}`,
      body,
      (key) =>
        salesApi().confirmMapping(order.case_id, line.line_no, body, key),
      `Đã xác nhận mã ${code} cho dòng ${line.line_no}`,
    );
    if (result.ok) {
      onDone();
      onClose();
    } else setError(result.error);
  };

  return (
    <Modal
      open
      width="min(960px, 100vw)"
      title={`Chọn mã PRV · dòng ${line.line_no}`}
      onCancel={onClose}
      cancelText="Hủy"
      okText={code ? `Xác nhận mã ${code}` : "Xác nhận mã"}
      okButtonProps={{
        disabled: !code || (typing && !PRV_CODE.test(code)),
        loading: pending !== null,
      }}
      onOk={confirm}
      destroyOnHidden
    >
      <Space orientation="vertical" className="w-full">
        <Typography.Paragraph className="!mb-0">
          <Typography.Text strong>Trên PO: </Typography.Text>
          {line.customer_item_code} · {line.description}{" "}
          <Button
            size="small"
            type="link"
            icon={<EyeOutlined aria-hidden />}
            onClick={() => onOpenSource("description", line.line_no)}
          >
            Xem nguồn
          </Button>
        </Typography.Paragraph>
        <Typography.Text>
          Trạng thái mã: {label(MAPPING_STATUS, line.mapping.status)}
        </Typography.Text>
        {typing ? (
          <Form layout="vertical">
            <Form.Item
              label="Mã PRV có trong danh mục mã hàng"
              extra="Dòng này không có mã ứng viên. Nhập mã Design đã tạo; mã nhập tay ghi tên bạn và cần người khác kiểm chéo."
              validateStatus={
                typed && !PRV_CODE.test(typed.trim()) ? "error" : undefined
              }
              help={
                typed && !PRV_CODE.test(typed.trim())
                  ? "Mã PRV gồm chữ in hoa, số và dấu '-' (2–32 ký tự)."
                  : undefined
              }
            >
              <Input
                value={typed}
                onChange={(e) => setTyped(e.target.value.toUpperCase())}
                maxLength={32}
              />
            </Form.Item>
          </Form>
        ) : (
          <Radio.Group
            aria-label="Mã ứng viên"
            value={picked}
            onChange={(e) => setPicked(e.target.value as string)}
            options={candidates.map((c) => ({ value: c, label: c }))}
          />
        )}
        {items.error ? (
          <RegionState error={items.error} onRetry={items.reload} />
        ) : null}
        {shown.length ? (
          <Table<Row>
            size="small"
            rowKey="key"
            pagination={false}
            loading={items.loading}
            scroll={{ x: "max-content" }}
            dataSource={rows(line, shown, byCode)}
            columns={[
              { title: "Thuộc tính", dataIndex: "attribute" },
              { title: "Trên PO", dataIndex: "po" },
              ...shown.map((c) => ({
                title: c,
                key: c,
                render: (_: unknown, row: Row) => (
                  <Space size={4}>
                    <span>{row.values[c]?.text ?? "Không rõ"}</span>
                    {fit(row.values[c]?.fits ?? null)}
                  </Space>
                ),
              })),
            ]}
          />
        ) : null}
        {typing &&
        code &&
        PRV_CODE.test(code) &&
        items.data &&
        !byCode.has(code) ? (
          <Alert
            type="warning"
            showIcon
            title={`Mã ${code} không có trong danh mục mã hàng: máy chủ sẽ từ chối.`}
          />
        ) : null}
        <ActionError error={error} />
      </Space>
    </Modal>
  );
}

function rows(line: Line, codes: string[], byCode: Map<string, Item>): Row[] {
  const qty = Number(line.quantity);
  const each = (pick: (item: Item) => { text: string; fits: boolean | null }) =>
    Object.fromEntries(
      codes.map((c) => {
        const item = byCode.get(c);
        return [
          c,
          item ? pick(item) : { text: "Không có trong danh mục", fits: false },
        ];
      }),
    );
  return [
    {
      key: "spec",
      attribute: "Số spec",
      po: "Trong mô tả",
      values: each((i) => ({ text: i.spec_no, fits: null })),
    },
    {
      key: "family",
      attribute: "Họ cáp",
      po: "Trong mô tả",
      values: each((i) => ({ text: i.family ?? "Không rõ", fits: null })),
    },
    {
      key: "cores",
      attribute: "Số lõi",
      po: "Trong mô tả",
      values: each((i) => ({ text: String(i.cores), fits: null })),
    },
    {
      key: "gauge",
      attribute: "Tiết diện",
      po: "Trong mô tả",
      values: each((i) => ({ text: i.gauge, fits: null })),
    },
    {
      key: "uom",
      attribute: "Đơn vị tính",
      po: line.uom,
      values: each((i) => ({
        text: i.uom ?? "Không rõ",
        fits: i.uom === null ? null : i.uom === line.uom,
      })),
    },
    {
      key: "moq",
      attribute: "Số lượng ≥ MOQ",
      po: formatQuantity(line.quantity),
      values: each((i) => ({
        text: formatQuantity(i.moq),
        fits: qty >= Number(i.moq),
      })),
    },
    {
      key: "pack",
      attribute: "Chẵn quy cách đóng gói",
      po: formatQuantity(line.quantity),
      values: each((i) => ({
        text: formatQuantity(i.pack_multiple),
        fits:
          Number(i.pack_multiple) > 0
            ? qty % Number(i.pack_multiple) === 0
            : null,
      })),
    },
    {
      key: "lt",
      attribute: "Lead time chuẩn",
      po: "Không có trên PO",
      values: each((i) => ({
        text: `${i.standard_lead_time_days} ngày`,
        fits: null,
      })),
    },
  ];
}
