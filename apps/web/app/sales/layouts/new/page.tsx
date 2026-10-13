"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Alert,
  Card,
  Empty,
  Form,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { formatDate } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import {
  LAYOUT_FIELDS,
  problemText,
  type Mapping,
  type MappingField,
} from "../../_lib/layouts";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { salesCrumbs } from "../../_components/crumbs";
import { GuardedButton } from "../../_components/guarded-button";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";
import { useAuth } from "../../../../lib/auth/auth-context";

type Source = SalesSchemas["LayoutSourceView"];
type Preview = SalesSchemas["LayoutPreviewView"];
type Values = Partial<Record<MappingField, string>> & {
  thousands_separator?: Mapping["thousands_separator"];
  decimal_separator?: Mapping["decimal_separator"];
  date_format?: Mapping["date_format"];
};

const DATE_FORMATS: Mapping["date_format"][] = [
  "%d/%m/%Y",
  "%Y-%m-%d",
  "%d-%m-%Y",
  "%m/%d/%Y",
  "%d.%m.%Y",
  "%Y/%m/%d",
];
const THOUSANDS: { value: Mapping["thousands_separator"]; label: string }[] = [
  { value: ",", label: "dấu phẩy (1,200)" },
  { value: ".", label: "dấu chấm (1.200)" },
  { value: " ", label: "khoảng trắng (1 200)" },
  { value: "none", label: "không nhóm (1200)" },
];

/**
 * Thiết lập mẫu PO (ticket 30): a customer's form no layout reads, mapped
 * once by a person. Each field takes one label printed on the form, picked
 * from the form's own cells; "Xem thử" reads the form with the mapping and
 * says every check it fails; "Gửi duyệt" stores it for a second person
 * (Trưởng bộ phận Sales) to approve. Where a model pre-filled the mapping,
 * the fields open with its labels, marked as a machine's, and the person
 * checks each against the form.
 */
export default function LayoutOnboardingPage() {
  return (
    <ScopeGate scope={SCOPE.prepare}>
      <Suspense>
        <Onboarding />
      </Suspense>
    </ScopeGate>
  );
}

function Onboarding() {
  const params = useSearchParams();
  const messageId = params.get("message") ?? "";
  const attachmentId = params.get("attachment") ?? "";
  const source = useResource(
    `sales/layouts/source/${messageId}/${attachmentId}`,
    useCallback(
      () => salesApi().layoutSource(messageId, attachmentId),
      [messageId, attachmentId],
    ),
  );
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Thiết lập mẫu PO")}
        title="Thiết lập mẫu PO"
        subtitle={
          source.data
            ? `Khách ${source.data.customer_code} · tệp ${source.data.kind === "pdf" ? "PDF" : "Excel"} của thư ${messageId}. Gán mỗi trường với nhãn in trên mẫu; người thứ hai duyệt trước khi DW1 đọc các PO sau theo mẫu này.`
            : "Gán mỗi trường của PO với nhãn in trên mẫu của khách."
        }
      />
      {!messageId || !attachmentId ? (
        <Empty description="Mở trang này từ một thư trong Hộp thư: thư đó cho biết tệp cần lập mẫu." />
      ) : source.error ? (
        <LoadError error={source.error} onRetry={source.reload} />
      ) : source.data ? (
        <MappingForm
          source={source.data}
          messageId={messageId}
          attachmentId={attachmentId}
        />
      ) : (
        <Card loading />
      )}
    </div>
  );
}

function MappingForm({
  source,
  messageId,
  attachmentId,
}: {
  source: Source;
  messageId: string;
  attachmentId: string;
}) {
  const { hasScope } = useAuth();
  const [form] = Form.useForm<Values>();
  // Every field, as typed: a preview counts only for the mapping it read.
  const watched = Form.useWatch([], form) as Values | undefined;
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [preview, setPreview] = useState<{
    of: string;
    result: Preview;
  } | null>(null);
  const [proposed, setProposed] = useState<string | null>(null);
  const prefill = source.prefill;
  const prefilled = prefill?.outcome === "proposed" ? prefill.mapping : null;
  const options = useMemo(
    () =>
      [...new Set(source.cells.map((c) => c.text))].map((text) => ({
        value: text,
        label: text,
      })),
    [source.cells],
  );
  const initial: Values = prefilled
    ? Object.fromEntries(
        Object.entries(prefilled).filter(([, v]) => v !== null),
      )
    : {
        thousands_separator: ",",
        decimal_separator: ".",
        date_format: "%d/%m/%Y",
      };

  const mapping = (values: Values): Mapping =>
    ({
      ...values,
      kind: source.kind,
      revision: values.revision || null,
      page_label: source.kind === "pdf" ? null : values.page_label || null,
      thousands_separator: values.thousands_separator ?? ",",
      decimal_separator: values.decimal_separator ?? ".",
      date_format: values.date_format ?? "%d/%m/%Y",
    }) as Mapping;

  const body = () => ({
    message_id: messageId,
    attachment_id: attachmentId,
    mapping: mapping(form.getFieldsValue()),
  });

  const check = async () => {
    const sent = body();
    const result = await run(
      "preview",
      sent,
      (key) => salesApi().previewLayout(sent, key),
      "Đã đọc thử mẫu với cách gán này",
    );
    if (result.ok) {
      setError(null);
      setPreview({ of: JSON.stringify(sent.mapping), result: result.value });
    } else setError(result.error);
  };

  const propose = async () => {
    const sent = body();
    const result = await run(
      "propose",
      sent,
      (key) => salesApi().proposeLayout(sent, key),
      "Đã gửi mẫu PO để duyệt",
    );
    if (result.ok) {
      setError(null);
      setProposed(result.value.layout_id);
    } else setError(result.error);
  };

  const current = JSON.stringify(mapping(watched ?? initial));
  const checkedNow = preview?.of === current && preview.result.ok;
  const proposeReason = !hasScope(SCOPE.prepare)
    ? "Bạn không có quyền lập mẫu PO (cần vai Sales phụ trách)."
    : !checkedNow
      ? "Bấm “Xem thử” với cách gán hiện tại; chỉ gửi duyệt khi mọi kiểm tra đạt."
      : null;

  return (
    <div className="space-y-4">
      {prefill ? (
        prefill.outcome === "proposed" ? (
          <Alert
            type="warning"
            showIcon
            title="Mô hình đã gợi ý cách gán: các trường mở sẵn nhãn mô hình chọn."
            description={`Mỗi nhãn là gợi ý của máy (${prefill.prompt}, hồ sơ ${prefill.model_profile}), đã qua mọi kiểm tra của DW1 nhưng chưa ai xác nhận. Đối chiếu từng trường với mẫu rồi mới gửi duyệt.`}
          />
        ) : (
          <Alert
            type="info"
            showIcon
            title="Mô hình không gợi ý được cách gán: các trường để trống, bạn gán tay."
            description={
              prefill.problems.length
                ? `DW1 từ chối gợi ý vì: ${prefill.problems.map(problemText).join("; ")}.`
                : "Mô hình không trả lời được."
            }
          />
        )
      ) : null}
      {source.approved ? (
        <Alert
          type="info"
          showIcon
          title={`Khách ${source.customer_code} đã có mẫu ${source.kind === "pdf" ? "PDF" : "Excel"} được duyệt (phiên bản ${source.approved.version}).`}
          description="Mẫu bạn gửi chỉ thay mẫu đó khi được duyệt."
        />
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card size="small" title="Các ô chữ trên mẫu">
          <Table
            size="small"
            rowKey="ref"
            pagination={false}
            scroll={{ y: 520, x: "max-content" }}
            dataSource={source.cells}
            locale={{ emptyText: "Mẫu không có ô chữ nào DW1 đọc được." }}
            columns={[
              { title: "Vị trí", dataIndex: "ref", width: 110 },
              { title: "Chữ in trên mẫu", dataIndex: "text" },
            ]}
          />
        </Card>
        <Card size="small" title="Gán trường với nhãn">
          <Form form={form} layout="vertical" initialValues={initial}>
            {LAYOUT_FIELDS.filter(
              (f) => !(source.kind === "pdf" && f.pdf === false),
            ).map(({ field, label, optional }) => (
              <Form.Item
                key={field}
                name={field}
                label={
                  <Space size="small">
                    {label}
                    {prefilled && prefilled[field] ? (
                      <StatusTag tone="warn">Mô hình gợi ý</StatusTag>
                    ) : null}
                  </Space>
                }
                rules={
                  optional
                    ? []
                    : [{ required: true, message: `${label} là bắt buộc` }]
                }
              >
                <Select
                  showSearch
                  allowClear
                  options={options}
                  placeholder={
                    optional ? "Mẫu không in (để trống)" : "Chọn nhãn"
                  }
                />
              </Form.Item>
            ))}
            {source.kind === "pdf" ? (
              <>
                <Form.Item
                  name="thousands_separator"
                  label="Cách nhóm hàng nghìn"
                >
                  <Select options={THOUSANDS} />
                </Form.Item>
                <Form.Item name="decimal_separator" label="Dấu thập phân">
                  <Select
                    options={[
                      { value: ".", label: "dấu chấm (0.5)" },
                      { value: ",", label: "dấu phẩy (0,5)" },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="date_format" label="Cách viết ngày">
                  <Select
                    options={DATE_FORMATS.map((f) => ({
                      value: f,
                      label: f
                        .replace("%d", "dd")
                        .replace("%m", "mm")
                        .replace("%Y", "yyyy"),
                    }))}
                  />
                </Form.Item>
              </>
            ) : null}
          </Form>
          <Space wrap>
            <GuardedButton
              loading={pending === "preview"}
              reason={null}
              onClick={check}
            >
              Xem thử
            </GuardedButton>
            <GuardedButton
              type="primary"
              loading={pending === "propose"}
              reason={proposed ? "Đã gửi duyệt." : proposeReason}
              onClick={propose}
            >
              Gửi duyệt
            </GuardedButton>
          </Space>
          <ActionError error={error} />
          {proposed ? (
            <Alert
              className="mt-3"
              type="success"
              showIcon
              title="Đã gửi mẫu để duyệt."
              description={
                <Link href="/sales/layouts">
                  Mở danh sách mẫu PO: Trưởng bộ phận Sales duyệt tại đó
                </Link>
              }
            />
          ) : null}
        </Card>
      </div>
      {preview ? <PreviewCard preview={preview.result} /> : null}
    </div>
  );
}

function PreviewCard({ preview }: { preview: Preview }) {
  return (
    <Card size="small" title="Đọc thử với cách gán này">
      {preview.ok ? (
        <Alert
          type="success"
          showIcon
          title={`Mọi kiểm tra đạt: đọc được PO ${preview.po_no} ngày ${preview.po_date ? formatDate(preview.po_date) : ""}, ${preview.lines.length} dòng, tổng ${preview.total ?? ""} ${preview.currency ?? ""}.`}
        />
      ) : (
        <Alert
          type="error"
          showIcon
          title="Cách gán chưa đọc đúng mẫu:"
          description={
            <ul className="m-0 pl-5">
              {preview.problems.map((p) => (
                <li key={p}>{problemText(p)}</li>
              ))}
            </ul>
          }
        />
      )}
      {preview.lines.length ? (
        <Table
          className="mt-3"
          size="small"
          rowKey="line_no"
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={preview.lines}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            { title: "Mã hàng", dataIndex: "customer_item_code" },
            { title: "Mô tả", dataIndex: "description" },
            { title: "Số lượng", dataIndex: "quantity", align: "right" },
            { title: "ĐVT", dataIndex: "uom" },
            { title: "Đơn giá", dataIndex: "unit_price", align: "right" },
            { title: "Thành tiền", dataIndex: "amount", align: "right" },
            {
              title: "Ngày giao",
              dataIndex: "requested_date",
              render: (v: string | null) => (v ? formatDate(v) : "Không in"),
            },
          ]}
        />
      ) : null}
      <Typography.Paragraph className="!mb-0 mt-2">
        Đây là bản đọc thử để đối chiếu với mẫu gốc; các PO đầu tiên đọc theo
        mẫu mới vẫn được Sales xác nhận từng giá trị.
      </Typography.Paragraph>
    </Card>
  );
}
