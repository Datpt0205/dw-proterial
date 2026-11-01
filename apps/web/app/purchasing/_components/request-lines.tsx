"use client";

import type { Dayjs } from "dayjs";
import { Button, Card, DatePicker, Flex, Form, Input } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import type { PurchasingSchemas } from "@dw/api-client";
import { fromPickerDay } from "../../../lib/dates";
import { parseAmountInput } from "../../../lib/money";

/**
 * A request's lines, as both forms ask them: a requester's ("Tôi cần mua…")
 * and a buyer's typing a paper request. One component so the two ask the
 * same fields with the same checks; the buyer's adds the item code.
 */
export interface LineFields {
  item_code?: string;
  description: string;
  quantity: string;
  unit: string;
  need_by?: Dayjs | null;
  estimated_unit_price?: string;
}

export const decimal = (label: string) => ({
  validator: (_: unknown, value: string | undefined) =>
    !value || parseAmountInput(value) !== null
      ? Promise.resolve()
      : Promise.reject(new Error(`${label} phải là một số, ví dụ 12,5`)),
});

/** The lines as the API takes them, numbered in the order shown. */
export function linesOut(
  lines: LineFields[],
): PurchasingSchemas["PrLine-Input"][] {
  return lines.map((l, i) => ({
    line_no: i + 1,
    item_code: l.item_code?.trim() || null,
    description: l.description.trim(),
    quantity: parseAmountInput(l.quantity)!,
    unit: l.unit.trim(),
    need_by: fromPickerDay(l.need_by),
    estimated_unit_price: l.estimated_unit_price
      ? parseAmountInput(l.estimated_unit_price)
      : null,
  }));
}

export function RequestLines({
  withItemCode = false,
}: {
  withItemCode?: boolean;
}) {
  return (
    <Form.List name="lines">
      {(rows, { add, remove }) => (
        <Flex vertical gap={8}>
          {rows.map((row, index) => (
            <Card
              key={row.key}
              size="small"
              title={`Dòng ${index + 1}`}
              extra={
                <Button
                  type="text"
                  icon={<DeleteOutlined aria-hidden />}
                  aria-label={`Bỏ dòng ${index + 1}`}
                  onClick={() => remove(row.name)}
                />
              }
            >
              <Flex gap={12} wrap>
                {withItemCode ? (
                  <Form.Item name={[row.name, "item_code"]} label="Mã hàng">
                    <Input maxLength={40} className="w-32" />
                  </Form.Item>
                ) : null}
                <Form.Item
                  name={[row.name, "description"]}
                  label="Mô tả"
                  rules={[{ required: true, message: "Ghi mô tả hàng" }]}
                  className="min-w-64 grow"
                >
                  <Input maxLength={500} />
                </Form.Item>
                <Form.Item
                  name={[row.name, "quantity"]}
                  label="Số lượng"
                  rules={[
                    { required: true, message: "Ghi số lượng" },
                    decimal("Số lượng"),
                  ]}
                >
                  <Input inputMode="decimal" />
                </Form.Item>
                <Form.Item
                  name={[row.name, "unit"]}
                  label="Đơn vị"
                  rules={[{ required: true, message: "Ghi đơn vị" }]}
                >
                  <Input maxLength={20} placeholder="hộp" />
                </Form.Item>
                <Form.Item name={[row.name, "need_by"]} label="Ngày cần">
                  <DatePicker format="DD/MM/YYYY" />
                </Form.Item>
                <Form.Item
                  name={[row.name, "estimated_unit_price"]}
                  label="Giá ước tính / đơn vị"
                  rules={[decimal("Giá ước tính")]}
                >
                  <Input inputMode="decimal" />
                </Form.Item>
              </Flex>
            </Card>
          ))}
          <Flex>
            <Button icon={<PlusOutlined aria-hidden />} onClick={() => add({})}>
              Thêm dòng
            </Button>
          </Flex>
        </Flex>
      )}
    </Form.List>
  );
}
