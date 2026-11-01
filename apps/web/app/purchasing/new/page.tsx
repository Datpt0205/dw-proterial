"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Dayjs } from "dayjs";
import {
  Alert,
  App,
  Button,
  Card,
  DatePicker,
  Flex,
  Form,
  Input,
} from "antd";
import {
  DeleteOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
} from "@ant-design/icons";
import type { PurchaseMyRequest, PurchaseRequestDraft } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { fromPickerDay, toPickerDay } from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { formatAmountInput, parseAmountInput } from "../../../lib/money";
import { purchasingApi } from "../_lib/api";
import { mailReason } from "../_lib/labels";
import { SCOPE } from "../_lib/scopes";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";
import { MarkTag } from "../_components/tags";

/**
 * "Tôi cần mua…": a requester writes what they need in their own words; DW2's
 * model reads them into a draft (only what the words say, whole lines or
 * none), the requester corrects it and presses "Gửi". Nothing is stored until
 * then. The number, the name and the department are the platform's, never
 * typed. A sentence the model cannot read says so; the form is still there to
 * fill by hand.
 */
export default function NewRequestPage() {
  return (
    <ScopeGate scope={[SCOPE.create]}>
      <NewRequest />
    </ScopeGate>
  );
}

interface LineFields {
  description: string;
  quantity: string;
  unit: string;
  need_by?: Dayjs | null;
  estimated_unit_price?: string;
}

interface Fields {
  lines: LineFields[];
  currency: string;
  budget_code?: string;
  need_by?: Dayjs | null;
  note?: string;
}

const MISSING: Record<string, string> = {
  budget_code: "mã ngân sách",
  need_by: "ngày cần hàng",
  estimated_unit_price: "giá ước tính",
};

const decimal = (label: string) => ({
  validator: (_: unknown, value: string | undefined) =>
    !value || parseAmountInput(value) !== null
      ? Promise.resolve()
      : Promise.reject(new Error(`${label} phải là một số, ví dụ 12,5`)),
});

function NewRequest() {
  const router = useRouter();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [form] = Form.useForm<Fields>();
  const [words, setWords] = useState("");
  const [draft, setDraft] = useState<PurchaseRequestDraft | null>(null);
  const [reading, setReading] = useState(false);
  const [sending, setSending] = useState(false);
  const [problems, setProblems] = useState(0);
  const [unread, setUnread] = useState<string | null>(null);
  // What the form opens with: set before it mounts, so it is its initial
  // values (a form not yet on screen keeps no `setFieldsValue`), and each
  // reading remounts it.
  const [initial, setInitial] = useState<Partial<Fields>>({});
  const [reads, setReads] = useState(0);

  async function read() {
    setReading(true);
    setUnread(null);
    setReads((n) => n + 1);
    try {
      const answer = await purchasingApi().draftMine(words.trim());
      setDraft(answer);
      if (answer.draft) {
        setInitial({
          currency: answer.draft.currency,
          budget_code: answer.draft.budget_code ?? undefined,
          need_by: toPickerDay(answer.draft.need_by ?? null),
          note: words.trim(),
          lines: answer.draft.lines.map((l) => ({
            description: l.description,
            quantity: formatAmountInput(l.quantity),
            unit: l.unit,
            need_by: toPickerDay(l.need_by ?? null),
            estimated_unit_price: l.estimated_unit_price
              ? formatAmountInput(l.estimated_unit_price)
              : undefined,
          })),
        });
      } else {
        // The rules' default currency is the server's: a send without one
        // is refused there, so the field is left for the person.
        setInitial({ note: words.trim(), lines: [{}] as LineFields[] });
      }
    } catch (error) {
      // DW2 could not read the words (no model, or one that did not answer):
      // say why where the form is, and open it empty to fill by hand, never
      // a toast that disappears with nothing to do next.
      setUnread(errorMessage(error));
      setDraft({ draft: null, missing: [], not_read: null });
      setInitial({ note: words.trim(), lines: [{}] as LineFields[] });
    } finally {
      setReading(false);
    }
  }

  async function send(fields: Fields) {
    const request: PurchaseMyRequest = {
      currency: fields.currency,
      budget_code: fields.budget_code?.trim() || null,
      need_by: fromPickerDay(fields.need_by),
      note: fields.note?.trim() ?? "",
      lines: fields.lines.map((l, i) => ({
        line_no: i + 1,
        description: l.description.trim(),
        quantity: parseAmountInput(l.quantity)!,
        unit: l.unit.trim(),
        need_by: fromPickerDay(l.need_by),
        estimated_unit_price: l.estimated_unit_price
          ? parseAmountInput(l.estimated_unit_price)
          : null,
      })),
    };
    setSending(true);
    try {
      const change = await purchasingApi().sendMine(
        request,
        keys.keyFor("send", request),
      );
      keys.settle("send");
      message.success("Đã gửi yêu cầu mua hàng");
      router.push(`/purchasing/requests/${change.case_id}`);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Tôi cần mua…")}
        title="Tôi cần mua…"
        help="Viết điều bạn cần như khi nhắn cho phòng Mua hàng. DW2 soạn yêu cầu, bạn xem lại rồi gửi. Số yêu cầu, tên và bộ phận của bạn do hệ thống điền."
      />
      <Card size="small">
        <Flex vertical gap={8}>
          <Input.TextArea
            aria-label="Bạn cần mua gì"
            placeholder="Ví dụ: Cần 20 hộp găng tay nitrile cỡ M cho xưởng 2 trước ngày 15/11, mã ngân sách SX-2026"
            autoSize={{ minRows: 3, maxRows: 8 }}
            maxLength={2000}
            showCount
            value={words}
            onChange={(event) => setWords(event.target.value)}
          />
          <Flex>
            <Button
              type="primary"
              size="large"
              icon={<RobotOutlined aria-hidden />}
              loading={reading}
              disabled={!words.trim()}
              onClick={() => void read()}
            >
              DW2 soạn yêu cầu
            </Button>
          </Flex>
        </Flex>
      </Card>
      {draft ? (
        <Card
          size="small"
          title={
            <Flex gap={8} align="center" wrap>
              <span>Yêu cầu sẽ gửi</span>
              {draft.draft ? (
                <MarkTag
                  mark="machine_read"
                  tip="DW2 đọc từ lời bạn viết; sửa nếu chưa đúng."
                />
              ) : null}
            </Flex>
          }
        >
          <Flex vertical gap={12}>
            {unread ? <Alert type="warning" showIcon title={unread} /> : null}
            {draft.not_read ? (
              <Alert
                type="warning"
                showIcon
                title="DW2 chưa đọc được lời này"
                description={`Vì ${mailReason(draft.not_read)}. Bạn có thể điền tay bên dưới.`}
              />
            ) : null}
            {draft.missing.length ? (
              <Alert
                type="info"
                showIcon
                title={`Quy tắc của công ty cần thêm: ${draft.missing.map((m) => MISSING[m] ?? m).join(", ")}`}
              />
            ) : null}
            {problems ? (
              <Alert
                type="error"
                showIcon
                title={`Còn ${problems} trường cần sửa`}
              />
            ) : null}
            <Form<Fields>
              key={reads}
              form={form}
              initialValues={initial}
              layout="vertical"
              validateTrigger="onBlur"
              scrollToFirstError={{ focus: true }}
              onFinish={(fields) => {
                setProblems(0);
                void send(fields);
              }}
              onFinishFailed={({ errorFields }) =>
                setProblems(errorFields.length)
              }
            >
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
                          <Form.Item
                            name={[row.name, "description"]}
                            label="Mô tả"
                            rules={[
                              { required: true, message: "Ghi mô tả hàng" },
                            ]}
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
                          <Form.Item
                            name={[row.name, "need_by"]}
                            label="Ngày cần"
                          >
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
                      <Button
                        icon={<PlusOutlined aria-hidden />}
                        onClick={() => add({})}
                      >
                        Thêm dòng
                      </Button>
                    </Flex>
                  </Flex>
                )}
              </Form.List>
              <Flex gap={12} wrap className="mt-4">
                <Form.Item
                  name="currency"
                  label="Loại tiền"
                  rules={[{ required: true, message: "Ghi loại tiền" }]}
                >
                  <Input maxLength={3} className="w-24" />
                </Form.Item>
                <Form.Item name="budget_code" label="Mã ngân sách">
                  <Input maxLength={40} />
                </Form.Item>
                <Form.Item name="need_by" label="Ngày cần hàng (cả yêu cầu)">
                  <DatePicker format="DD/MM/YYYY" />
                </Form.Item>
              </Flex>
              <Form.Item name="note" label="Ghi chú cho phòng Mua hàng">
                <Input.TextArea
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  maxLength={2000}
                />
              </Form.Item>
              <Button
                type="primary"
                size="large"
                htmlType="submit"
                icon={<SendOutlined aria-hidden />}
                loading={sending}
              >
                Gửi
              </Button>
            </Form>
          </Flex>
        </Card>
      ) : null}
    </div>
  );
}
