"use client";

import { useCallback, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Collapse,
  DatePicker,
  Drawer,
  Flex,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { MinusCircleOutlined, PlusOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import type { SalesSchemas } from "@dw/api-client";
import { InfoTip } from "@dw/ui";
import { fromPickerDay, toPickerDay } from "../../../../lib/dates";
import { useCachedResource } from "../../../../lib/use-cached-resource";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { INTERNAL_REASON, label } from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { useAction } from "../../_lib/use-action";
import { GuardedButton } from "../../_components/guarded-button";

type Order = SalesSchemas["OrderCaseView"];
type ReadView = SalesSchemas["InternalReadView"];
type ReadLine = ReadView["lines"][number];
type Reason = keyof typeof INTERNAL_REASON;

const PREPARE = "sales.order.prepare";
const NO_SCOPE =
  "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách).";
const PROBLEM: Record<NonNullable<ReadLine["problem"]>, string> = {
  no_such_line: "Đơn không có dòng này",
  unread: "Cần nhập: thư chưa rõ",
  quantity_raised: "Nhiều hơn số lượng khách đặt",
  printed_schedules: "Dòng in sẵn các đợt: chỉ dời ngày",
};

interface DeliveryForm {
  quantity: number | null;
  date: Dayjs | null;
}
interface LineForm {
  line_no: number | null;
  // PC cancels the whole line (W07): no delivery is sent for it.
  cancelled?: boolean;
  deliveries: DeliveryForm[];
  // What DW1 read leaves to a person, shown beside the line.
  problem?: string;
}
interface Values {
  reason: Reason | null;
  lines: LineForm[];
}

/** One read line as the form's line: what the paste left open stays empty. */
function formLine(line: ReadLine): LineForm {
  return {
    line_no: line.line_no ?? null,
    deliveries: line.deliveries.map((d) => ({
      quantity: d.quantity === null ? null : Number(d.quantity),
      date: toPickerDay(d.date),
    })),
    problem: line.problem ? PROBLEM[line.problem] : undefined,
  };
}

/**
 * "Thay đổi nội bộ" (ticket 10, BA step 6.1B): PC moves, splits or cuts
 * lines of a confirmed order. Sales pastes PC's mail, DW1 reads it into the
 * form (nothing is kept), Sales checks each line and presses "Áp dụng", the
 * one action that changes the order: it then goes to its Bravo update, its
 * cross-check and its confirmation again, and the notice to the customer is
 * a draft in "Tài liệu". A line PC cancels whole is ticked "PC hủy cả dòng"
 * and carries no delivery; a line already cancelled is not offered. Offered
 * only where the server says the order takes one (`internal_change_open`);
 * the server refuses anyway.
 */
export function InternalChangePanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  if (!order.internal_change_open) return null;
  const may = viewer.hasScope(PREPARE);
  return (
    <Card size="small" title="Thay đổi nội bộ">
      <Space wrap>
        <GuardedButton
          reason={may ? null : NO_SCOPE}
          onClick={() => setOpen(true)}
        >
          Thay đổi nội bộ
        </GuardedButton>
        <InfoTip label="Thay đổi nội bộ">
          PC dời, tách hoặc cắt dòng sau khi đã xác nhận (quá tải, NG, thiếu
          hàng). Dán thư PC để DW1 điền từng dòng, kiểm rồi bấm Áp dụng: đơn
          chuyển sang cập nhật Bravo, kiểm chéo và xác nhận lại.
        </InfoTip>
      </Space>
      {open ? (
        <InternalChangeDrawer
          order={order}
          onClose={() => setOpen(false)}
          onDone={() => {
            setOpen(false);
            onChanged();
          }}
        />
      ) : null}
    </Card>
  );
}

function InternalChangeDrawer({
  order,
  onClose,
  onDone,
}: {
  order: Order;
  onClose: () => void;
  onDone: () => void;
}) {
  const { modal } = App.useApp();
  const [form] = Form.useForm<Values>();
  const { run, pending } = useAction();
  const [text, setText] = useState("");
  const [read, setRead] = useState<ReadView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(0);
  // The longest paste DW1 reads, as the API serves it (`pc_dates.MAX_TEXT`),
  // from the same cached listing item 7's reader uses.
  const limit = useCachedResource(
    `sales/pc-mails/${order.case_id}`,
    useCallback(() => salesApi().pcMails(order.case_id), [order.case_id]),
  );
  const version = order.case_version;
  const readId = `internal/read/${order.case_id}`;
  const applyId = `internal/apply/${order.case_id}`;
  const options = order.lines
    .filter((line) => !line.cancelled)
    .map((line) => ({
      value: line.line_no,
      label: `Dòng ${line.line_no}: ${line.customer_item_code}`,
    }));

  const readPaste = async () => {
    const result = await run(
      readId,
      { version, text },
      (key) => salesApi().readInternalChange(order.case_id, version, text, key),
      "DW1 đã đọc thư PC",
    );
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setRead(result.value);
    const lines = result.value.lines.filter((x) => x.line_no !== null);
    if (lines.length) form.setFieldValue("lines", lines.map(formLine));
  };

  const apply = (values: Values) => {
    const lines = values.lines.map((line) =>
      line.cancelled
        ? { line_no: line.line_no ?? 0, cancelled: true, deliveries: [] }
        : {
            line_no: line.line_no ?? 0,
            cancelled: false,
            deliveries: line.deliveries.map((d) => ({
              quantity: String(d.quantity ?? ""),
              date: fromPickerDay(d.date) ?? "",
            })),
          },
    );
    const cancelled = values.lines.filter((line) => line.cancelled).length;
    const body = {
      case_version: version,
      reason: values.reason ?? "other",
      lines,
    };
    modal.confirm({
      title: "Áp dụng thay đổi nội bộ",
      content: `PO ${order.po_no}: ${lines.length} dòng đổi theo lịch PC${cancelled ? `, trong đó ${cancelled} dòng hủy cả` : ""}. Đơn chuyển sang cập nhật Bravo, rồi kiểm chéo và xác nhận lại với khách.`,
      okText: "Áp dụng",
      cancelText: "Chưa áp dụng",
      autoFocusButton: "cancel",
      onOk: async () => {
        const result = await run(
          applyId,
          body,
          (key) => salesApi().applyInternalChange(order.case_id, body, key),
          "Đã áp dụng thay đổi nội bộ",
        );
        if (result.ok) onDone();
        else setError(result.error);
      },
    });
  };

  const said = (v: ReadView) =>
    v.status === "read"
      ? `Đã điền ${v.lines.filter((x) => x.line_no !== null).length} dòng từ thư PC (máy đọc): kiểm từng dòng trước khi áp dụng.` +
        (v.dropped ? ` ${v.dropped} dòng bị bỏ vì chữ không có trong thư.` : "")
      : v.status === "nothing"
        ? "DW1 không thấy dòng nào PC đổi trong thư này: nhập từng dòng."
        : v.status === "off"
          ? "Bước đọc thư PC đang tắt: nhập từng dòng."
          : "DW1 chưa đọc được lúc này: nhập từng dòng.";
  const refused = read?.lines.filter((x) => x.line_no === null) ?? [];

  return (
    <Drawer
      open
      size="large"
      title={`Thay đổi nội bộ · PO ${order.po_no}`}
      onClose={onClose}
      footer={
        <Flex justify="end" gap={8}>
          <Button onClick={onClose}>Hủy</Button>
          <Button
            type="primary"
            loading={pending === applyId}
            onClick={() => form.submit()}
          >
            Áp dụng
          </Button>
        </Flex>
      }
    >
      <Space orientation="vertical" className="w-full">
        <Collapse
          size="small"
          items={[
            {
              key: "paste",
              label: "Dán thư PC để DW1 điền các dòng",
              children: (
                <Flex vertical gap={8}>
                  <Input.TextArea
                    aria-label="Thư PC đổi lịch giao"
                    placeholder="Dán nội dung thư PC dời, tách hoặc cắt dòng"
                    autoSize={{ minRows: 3, maxRows: 10 }}
                    maxLength={limit.data?.text_max}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <div>
                    <Button
                      loading={pending === readId}
                      disabled={!text.trim()}
                      onClick={() => void readPaste()}
                    >
                      DW1 đọc thư PC
                    </Button>
                  </div>
                  {read ? (
                    <Typography.Text role="status">
                      {said(read)}
                    </Typography.Text>
                  ) : null}
                  {refused.length ? (
                    <Alert
                      type="warning"
                      showIcon
                      title="Thư nêu dòng đơn này không có (không điền)"
                      description={refused.map((x) => x.words).join(" · ")}
                    />
                  ) : null}
                </Flex>
              ),
            },
          ]}
        />
        {failed ? (
          <Alert type="error" showIcon title={`Còn ${failed} trường cần sửa`} />
        ) : null}
        <Form<Values>
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          scrollToFirstError={{ focus: true }}
          initialValues={{
            reason: null,
            lines: [
              { line_no: null, deliveries: [{ quantity: null, date: null }] },
            ],
          }}
          onFinishFailed={({ errorFields }) => setFailed(errorFields.length)}
          onFinish={(values) => {
            setFailed(0);
            apply(values);
          }}
        >
          <Form.Item
            name="reason"
            label="Lý do"
            rules={[{ required: true, message: "Chọn lý do" }]}
          >
            <Select
              className="max-w-xs"
              options={Object.keys(INTERNAL_REASON).map((code) => ({
                value: code,
                label: label(INTERNAL_REASON, code),
              }))}
            />
          </Form.Item>
          <Form.List name="lines">
            {(lines, { add, remove }) => (
              <Space orientation="vertical" className="w-full">
                {lines.map((line, index) => (
                  <Card
                    key={line.key}
                    size="small"
                    title={
                      <Space>
                        {`Dòng thay đổi ${index + 1}`}
                        <Form.Item noStyle shouldUpdate>
                          {() => {
                            const problem = form.getFieldValue([
                              "lines",
                              line.name,
                              "problem",
                            ]) as string | undefined;
                            return problem ? (
                              <Tag color="warning">{problem}</Tag>
                            ) : null;
                          }}
                        </Form.Item>
                      </Space>
                    }
                    extra={
                      lines.length > 1 ? (
                        <Button
                          icon={<MinusCircleOutlined aria-hidden />}
                          aria-label={`Bỏ dòng thay đổi ${index + 1}`}
                          onClick={() => remove(line.name)}
                        />
                      ) : null
                    }
                  >
                    <Form.Item
                      name={[line.name, "line_no"]}
                      label="Dòng của đơn"
                      rules={[{ required: true, message: "Chọn dòng" }]}
                    >
                      <Select className="max-w-md" options={options} />
                    </Form.Item>
                    <Form.Item
                      name={[line.name, "cancelled"]}
                      valuePropName="checked"
                    >
                      <Checkbox>PC hủy cả dòng</Checkbox>
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate>
                      {() =>
                        form.getFieldValue([
                          "lines",
                          line.name,
                          "cancelled",
                        ]) ? null : (
                          <Form.List name={[line.name, "deliveries"]}>
                            {(deliveries, more) => (
                              <>
                                {deliveries.map((d, n) => (
                                  <Space key={d.key} align="start" wrap>
                                    <Form.Item
                                      name={[d.name, "quantity"]}
                                      label={`Số lượng đợt ${n + 1}`}
                                      rules={[
                                        {
                                          required: true,
                                          message: "Cần số lượng",
                                        },
                                      ]}
                                    >
                                      <InputNumber
                                        min={0}
                                        decimalSeparator=","
                                      />
                                    </Form.Item>
                                    <Form.Item
                                      name={[d.name, "date"]}
                                      label={`Ngày PC đợt ${n + 1}`}
                                      rules={[
                                        {
                                          required: true,
                                          message: "Cần ngày PC",
                                        },
                                      ]}
                                    >
                                      <DatePicker format="DD/MM/YYYY" />
                                    </Form.Item>
                                    {deliveries.length > 1 ? (
                                      <Button
                                        className="mt-7"
                                        icon={
                                          <MinusCircleOutlined aria-hidden />
                                        }
                                        aria-label={`Bỏ đợt ${n + 1}`}
                                        onClick={() => more.remove(d.name)}
                                      />
                                    ) : null}
                                  </Space>
                                ))}
                                <Button
                                  icon={<PlusOutlined aria-hidden />}
                                  onClick={() =>
                                    more.add({ quantity: null, date: null })
                                  }
                                >
                                  Thêm một đợt
                                </Button>
                              </>
                            )}
                          </Form.List>
                        )
                      }
                    </Form.Item>
                  </Card>
                ))}
                <Button
                  icon={<PlusOutlined aria-hidden />}
                  onClick={() =>
                    add({
                      line_no: null,
                      deliveries: [{ quantity: null, date: null }],
                    })
                  }
                >
                  Thêm một dòng
                </Button>
              </Space>
            )}
          </Form.List>
        </Form>
        <ActionError error={error} />
      </Space>
    </Drawer>
  );
}
