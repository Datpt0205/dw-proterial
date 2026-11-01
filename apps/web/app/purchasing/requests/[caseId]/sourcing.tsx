"use client";

import { useCallback, useMemo, useState } from "react";
import {
  App,
  Button,
  Card,
  Collapse,
  DatePicker,
  Flex,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Table,
  Tooltip,
  Typography,
} from "antd";
import { CheckOutlined, MailOutlined, PlusOutlined } from "@ant-design/icons";
import type {
  PurchaseCase,
  PurchaseChoice,
  PurchaseComparison,
} from "@dw/api-client";
import { InfoTip } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { formatDate, fromPickerDay } from "../../../../lib/dates";
import { errorMessage } from "../../../../lib/error-message";
import { useIdempotencyKeys } from "../../../../lib/idempotency";
import { formatQuantity, parseAmountInput } from "../../../../lib/money";
import { useAuth } from "../../../../lib/auth/auth-context";
import { useCachedResource } from "../../../../lib/use-cached-resource";
import { purchasingApi } from "../../_lib/api";
import { money } from "../../_lib/format";
import { SCOPE } from "../../_lib/scopes";
import { MarkTag } from "../../_components/tags";

/**
 * Asking suppliers and choosing among them: the RFQs DW2 drafted (each with
 * who wrote it, the model or code's template; a buyer sends them, DW2 sends
 * nothing), the offers recorded (typed, or read from a supplier's verified
 * reply), and code's comparison, where a person picks one offer per line.
 * The cheapest offer that meets the need-by date is pre-chosen and says so:
 * it is code's arithmetic, not a judgement, and the person still presses.
 */
export function Sourcing({
  c,
  onChanged,
}: {
  c: PurchaseCase;
  onChanged: () => void;
}) {
  return (
    <>
      {c.rfq ? <RfqCard c={c} /> : null}
      {c.rfq ? <OffersCard c={c} onChanged={onChanged} /> : null}
      {c.offers.length ? <ComparisonCard c={c} onChanged={onChanged} /> : null}
    </>
  );
}

/**
 * The buyer names suppliers for a line (one the master data lists nobody
 * for, or one more): opened on a click, and by itself when drafting was
 * refused for want of a supplier. Codes only from the company's list; the
 * server checks each again.
 */
export function NamedSuppliers({
  c,
  named,
  onChange,
  open,
}: {
  c: PurchaseCase;
  named: Record<number, string[]>;
  onChange: (named: Record<number, string[]>) => void;
  open: boolean;
}) {
  const list = useCachedResource(
    "purchasing/suppliers",
    useCallback(() => purchasingApi().suppliers(), []),
  );
  const options = (list.data ?? []).map((s) => ({
    value: s.code,
    label: `${s.code} · ${s.name}`,
  }));
  return (
    <Collapse
      size="small"
      className="w-full"
      defaultActiveKey={open ? ["named"] : []}
      key={open ? "open" : "closed"}
      items={[
        {
          key: "named",
          label: "Chỉ định nhà cung cấp cho từng dòng",
          children: (
            <Flex vertical gap={8}>
              {list.error ? <LoadError error={list.error} compact /> : null}
              {c.request.lines.map((line) => (
                <Flex key={line.line_no} vertical gap={2}>
                  <Typography.Text>
                    Dòng {line.line_no} · {line.description}
                  </Typography.Text>
                  <Select
                    mode="multiple"
                    aria-label={`Nhà cung cấp cho dòng ${line.line_no}`}
                    placeholder="Chọn nhà cung cấp"
                    loading={list.loading}
                    options={options}
                    value={named[line.line_no] ?? []}
                    onChange={(codes: string[]) =>
                      onChange({ ...named, [line.line_no]: codes })
                    }
                  />
                </Flex>
              ))}
            </Flex>
          ),
        },
      ]}
    />
  );
}

function RfqCard({ c }: { c: PurchaseCase }) {
  const rfq = c.rfq!;
  return (
    <Card
      size="small"
      title={`Thư hỏi giá (${rfq.drafts.length}) · hạn trả lời ${formatDate(rfq.reply_by)}`}
    >
      <Flex vertical gap={8}>
        {rfq.unsourced.length ? (
          <Typography.Text>
            Dòng {rfq.unsourced.join(", ")} chưa có nhà cung cấp trong danh mục.
          </Typography.Text>
        ) : null}
        <Collapse
          size="small"
          items={rfq.drafts.map((d) => ({
            key: d.supplier_code,
            label: (
              <Flex gap={8} wrap align="center">
                <span>
                  {d.supplier_code} · dòng {d.line_nos.join(", ")}
                </span>
                <MarkTag
                  mark={
                    d.written_by === "model" ? "machine_written" : "template"
                  }
                  tip={
                    d.written_by === "model"
                      ? "DW2 viết thư này từ dữ liệu của hệ thống; không ghi số tiền nào."
                      : "Thư theo mẫu cố định, vì bản máy viết không qua được kiểm tra."
                  }
                />
              </Flex>
            ),
            children: (
              <Flex vertical gap={4}>
                <Typography.Text>
                  Gửi: {d.to.join(", ") || "Chưa có địa chỉ"}
                </Typography.Text>
                <Typography.Text strong>{d.subject}</Typography.Text>
                <Typography.Paragraph
                  className="mb-0"
                  style={{ whiteSpace: "pre-wrap" }}
                >
                  {d.body}
                </Typography.Paragraph>
              </Flex>
            ),
          }))}
        />
      </Flex>
    </Card>
  );
}

// -------------------------------------------------------------- offers --

interface OfferFields {
  supplier_code: string;
  line_no: number;
  unit_price: string;
  lead_time_days: number;
  valid_until?: import("dayjs").Dayjs | null;
}

function OffersCard({
  c,
  onChanged,
}: {
  c: PurchaseCase;
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [form] = Form.useForm<OfferFields>();
  const [pending, setPending] = useState<string | null>(null);
  const [mail, setMail] = useState<string | null>(null);
  const may = hasScope(SCOPE.rfq);
  const open = c.status === "rfq_drafted";
  const why = !may
    ? "Vai của bạn không gồm việc hỏi giá."
    : !open
      ? "Hồ sơ không còn ở bước hỏi giá."
      : null;

  const suppliers = [...new Set(c.rfq!.drafts.map((d) => d.supplier_code))];
  const mailbox = useCachedResource(
    `purchasing/mail:${may && open}`,
    useCallback(
      () => (may && open ? purchasingApi().mailbox() : Promise.resolve([])),
      [may, open],
    ),
  );
  const replies = (mailbox.data ?? []).filter((m) => m.case_id === null);

  async function record(fields: OfferFields) {
    const offer = {
      supplier_code: fields.supplier_code,
      line_no: fields.line_no,
      unit_price: parseAmountInput(fields.unit_price)!,
      currency: c.request.currency,
      lead_time_days: fields.lead_time_days,
      valid_until: fromPickerDay(fields.valid_until),
    };
    const id = `offer:${c.case_id}`;
    setPending("offer");
    try {
      await purchasingApi().recordOffer(
        c.case_id,
        c.case_version,
        offer,
        keys.keyFor(id, offer),
      );
      keys.settle(id);
      message.success("Đã ghi báo giá");
      form.resetFields();
      onChanged();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  async function readMail() {
    if (!mail) return;
    const id = `offer-mail:${c.case_id}:${mail}`;
    setPending("mail");
    try {
      await purchasingApi().readOfferMail(
        c.case_id,
        mail,
        c.case_version,
        keys.keyFor(id, null),
      );
      keys.settle(id);
      message.success("DW2 đã đọc báo giá trong thư");
      setMail(null);
      onChanged();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <Card size="small" title={`Báo giá đã ghi (${c.offers.length})`}>
      <Flex vertical gap={12}>
        <Table
          rowKey={(o) => `${o.supplier_code}:${o.line_no}:${o.recorded_at}`}
          size="small"
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={c.offers}
          locale={{
            emptyText:
              "Chưa có báo giá nào: ghi tay hoặc cho DW2 đọc thư trả lời của nhà cung cấp.",
          }}
          columns={[
            { title: "Nhà cung cấp", dataIndex: "supplier_code" },
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Đơn giá",
              key: "p",
              align: "right",
              render: (_, o) => money(o.unit_price, o.currency),
            },
            {
              title: "Giao trong",
              key: "l",
              render: (_, o) => `${o.lead_time_days} ngày`,
            },
            {
              title: "Hiệu lực đến",
              key: "v",
              render: (_, o) =>
                o.valid_until ? formatDate(o.valid_until) : "Không ghi",
            },
            {
              title: "Nguồn",
              key: "s",
              render: (_, o) => (
                <MarkTag
                  mark={o.source === "mail" ? "machine_read" : "person"}
                />
              ),
            },
          ]}
        />
        {open ? (
          <>
            <Typography.Text strong>Cho DW2 đọc thư trả lời</Typography.Text>
            {mailbox.error ? (
              <LoadError
                error={mailbox.error}
                compact
                onRetry={mailbox.reload}
              />
            ) : null}
            <Flex gap={8} wrap>
              <Select
                aria-label="Thư trả lời của nhà cung cấp"
                className="min-w-64"
                placeholder="Chọn thư trong hộp thư mua hàng"
                value={mail}
                onChange={setMail}
                loading={mailbox.loading}
                disabled={why !== null}
                notFoundContent="Không có thư nào chưa gắn với hồ sơ"
                options={replies.map((m) => ({
                  value: m.message_id,
                  label: `${m.sender} · ${m.subject}`,
                }))}
              />
              <Tooltip title={why ?? (mail ? null : "Chọn một thư trước.")}>
                <Button
                  icon={<MailOutlined aria-hidden />}
                  disabled={
                    why !== null ||
                    !mail ||
                    (pending !== null && pending !== "mail")
                  }
                  loading={pending === "mail"}
                  onClick={() => void readMail()}
                >
                  DW2 đọc báo giá
                </Button>
              </Tooltip>
            </Flex>
            <Typography.Text strong>Hoặc ghi tay</Typography.Text>
            <Form<OfferFields>
              form={form}
              layout="vertical"
              validateTrigger="onBlur"
              scrollToFirstError={{ focus: true }}
              disabled={why !== null}
              onFinish={(fields) => void record(fields)}
            >
              <Flex gap={12} wrap>
                <Form.Item
                  name="supplier_code"
                  label="Nhà cung cấp"
                  rules={[{ required: true, message: "Chọn nhà cung cấp" }]}
                >
                  <Select
                    className="min-w-40"
                    options={suppliers.map((s) => ({ value: s, label: s }))}
                  />
                </Form.Item>
                <Form.Item
                  name="line_no"
                  label="Dòng"
                  rules={[{ required: true, message: "Chọn dòng" }]}
                >
                  <Select
                    className="min-w-40"
                    options={c.request.lines.map((l) => ({
                      value: l.line_no,
                      label: `${l.line_no} · ${l.description}`,
                    }))}
                  />
                </Form.Item>
                <Form.Item
                  name="unit_price"
                  label={`Đơn giá (${c.request.currency})`}
                  rules={[
                    { required: true, message: "Ghi đơn giá" },
                    {
                      validator: (_, value: string | undefined) =>
                        !value || parseAmountInput(value) !== null
                          ? Promise.resolve()
                          : Promise.reject(
                              new Error(
                                "Đơn giá phải là một số, ví dụ 1.150.000",
                              ),
                            ),
                    },
                  ]}
                >
                  <Input inputMode="decimal" placeholder="1.150.000" />
                </Form.Item>
                <Form.Item
                  name="lead_time_days"
                  label="Giao trong (ngày)"
                  rules={[{ required: true, message: "Ghi số ngày giao" }]}
                >
                  <InputNumber min={0} max={365} precision={0} />
                </Form.Item>
                <Form.Item name="valid_until" label="Hiệu lực đến">
                  <DatePicker format="DD/MM/YYYY" />
                </Form.Item>
              </Flex>
              <Tooltip title={why}>
                <Button
                  htmlType="submit"
                  icon={<PlusOutlined aria-hidden />}
                  loading={pending === "offer"}
                  disabled={
                    why !== null || (pending !== null && pending !== "offer")
                  }
                >
                  Ghi báo giá
                </Button>
              </Tooltip>
            </Form>
          </>
        ) : null}
      </Flex>
    </Card>
  );
}

// ---------------------------------------------------------- comparison --

function ComparisonCard({
  c,
  onChanged,
}: {
  c: PurchaseCase;
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const view = useCachedResource<PurchaseComparison>(
    `purchasing/comparison/${c.case_id}/${c.case_version}`,
    useCallback(() => purchasingApi().comparison(c.case_id), [c.case_id]),
  );
  const proposed = useMemo(() => {
    const chosen: Record<number, string> = {};
    for (const line of view.data?.lines ?? []) {
      const best = line.offers.find((o) => o.meets_need_by) ?? line.offers[0];
      if (best) chosen[line.line_no] = best.supplier_code;
    }
    for (const choice of c.selection?.choices ?? [])
      chosen[choice.line_no] = choice.supplier_code;
    return chosen;
  }, [view.data, c.selection]);
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [pending, setPending] = useState(false);
  const choices: PurchaseChoice[] = Object.entries({
    ...proposed,
    ...picked,
  }).map(([line, supplier]) => ({
    line_no: Number(line),
    supplier_code: supplier,
  }));

  const open = c.status === "rfq_drafted";
  const lines = view.data?.lines ?? [];
  const unpriced = lines
    .filter((l) => l.offers.length === 0)
    .map((l) => l.line_no);
  const why = !hasScope(SCOPE.rfq)
    ? "Vai của bạn không gồm việc chọn nhà cung cấp."
    : !open
      ? "Hồ sơ không còn ở bước chọn nhà cung cấp."
      : unpriced.length
        ? `Dòng ${unpriced.join(", ")} chưa có báo giá hợp lệ.`
        : null;

  const total = lines.reduce((sum, line) => {
    const offer = line.offers.find(
      (o) => o.supplier_code === { ...proposed, ...picked }[line.line_no],
    );
    return offer ? sum + Number(offer.total) : sum;
  }, 0);

  async function select() {
    const id = `select:${c.case_id}`;
    setPending(true);
    try {
      const change = await purchasingApi().select(
        c.case_id,
        c.case_version,
        choices,
        keys.keyFor(id, choices),
      );
      keys.settle(id);
      message.success(
        change.status === "awaiting_reapproval"
          ? "Tổng vượt hạn mức đã duyệt: lựa chọn đã gửi duyệt lại"
          : "Đã chọn nhà cung cấp",
      );
      onChanged();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (view.error) return <LoadError error={view.error} onRetry={view.reload} />;
  const data = view.data;
  return (
    <Card size="small" title="So sánh báo giá" loading={view.loading && !data}>
      {data ? (
        <Flex vertical gap={12}>
          <Typography.Text>
            {data.approved_limit
              ? `Hạn mức đã duyệt: ${money(data.approved_limit, data.currency)}`
              : "Chưa có hạn mức đã duyệt"}{" "}
            <InfoTip label="Cách so sánh báo giá">
              Mỗi dòng: báo giá còn hạn bằng {data.currency}, rẻ nhất trước. DW2
              chọn sẵn báo giá rẻ nhất kịp ngày cần; bạn đổi được trước khi bấm.
              Tổng vượt hạn mức thì lựa chọn được gửi duyệt lại.
            </InfoTip>
          </Typography.Text>
          {lines.map((line) => (
            <Flex key={line.line_no} vertical gap={4}>
              <Typography.Text strong>
                Dòng {line.line_no} · {line.description} ·{" "}
                {formatQuantity(line.quantity)}
                {line.need_by ? ` · cần ${formatDate(line.need_by)}` : ""}
              </Typography.Text>
              {line.offers.length === 0 ? (
                <Typography.Text>Chưa có báo giá hợp lệ.</Typography.Text>
              ) : (
                <Radio.Group
                  aria-label={`Nhà cung cấp cho dòng ${line.line_no}`}
                  disabled={!open}
                  value={{ ...proposed, ...picked }[line.line_no]}
                  onChange={(event) =>
                    setPicked((p) => ({
                      ...p,
                      [line.line_no]: event.target.value as string,
                    }))
                  }
                >
                  <Flex vertical gap={4}>
                    {line.offers.map((o) => (
                      <Radio key={o.supplier_code} value={o.supplier_code}>
                        {o.supplier_code} · {money(o.unit_price, data.currency)}{" "}
                        / đv · tổng {money(o.total, data.currency)} · giao{" "}
                        {o.lead_time_days} ngày
                        {o.meets_need_by ? "" : " · không kịp ngày cần"}
                        {o.cheapest ? " · rẻ nhất" : ""}
                      </Radio>
                    ))}
                  </Flex>
                </Radio.Group>
              )}
            </Flex>
          ))}
          <Typography.Text strong>
            Tổng các báo giá đang chọn: {money(String(total), data.currency)}
          </Typography.Text>
          {open ? (
            <Flex gap={8} align="center" wrap>
              <Tooltip title={why}>
                <Button
                  type="primary"
                  size="large"
                  icon={<CheckOutlined aria-hidden />}
                  disabled={why !== null}
                  loading={pending}
                  onClick={() => void select()}
                >
                  Chọn các nhà cung cấp này
                </Button>
              </Tooltip>
              {why ? (
                <Typography.Text role="note">{why}</Typography.Text>
              ) : null}
            </Flex>
          ) : null}
        </Flex>
      ) : null}
    </Card>
  );
}
