"use client";

import { useCallback, useState, type ReactNode } from "react";
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Drawer,
  Flex,
  Form,
  Input,
  InputNumber,
  Radio,
  Segmented,
  Skeleton,
  Table,
  Typography,
  Upload,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  lastDays,
  toPickerDay,
} from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { salesApi } from "../_lib/api";
import { base64, SCAN_ACCEPT, SCAN_MAX_BYTES } from "../_lib/files";
import {
  EXPORT_CLASSIFICATION,
  EXPORT_NEED,
  label,
  SCREENING_OUTCOME,
} from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { saveBlob } from "../_components/artifacts-panel";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";

type Detail = SalesSchemas["CustomerDetailView"];
type Screening = SalesSchemas["ScreeningView"];
type Step = SalesSchemas["ScreeningStep"];
type Route = "denial-list" | "red-flag" | "noc" | "esf";
type ExportFile = Parameters<
  ReturnType<typeof salesApi>["exportControlFile"]
>[1];

const ROUTE: Record<Step, Route> = {
  denial_list: "denial-list",
  red_flag: "red-flag",
  noc: "noc",
  esf: "esf",
};

/**
 * One customer's export control: the product screen read from master data,
 * then each step a person records (denial list, red flag, NOEC/NOC, ESF and
 * its yearly renewal), its latest result with who recorded it and the
 * document it rests on. Recording needs `sales.compliance.ack`; without it
 * every form says so, and the server refuses anyway.
 */
export function CustomerDrawer({
  code,
  fiscalYear,
  onClose,
  onChanged,
}: {
  code: string;
  fiscalYear: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const detail = useResource(
    `sales/export-control/${code}`,
    useCallback(() => salesApi().exportControlCustomer(code), [code]),
  );
  const changed = () => {
    detail.reload();
    onChanged();
  };
  const data = detail.data;
  return (
    <Drawer
      open
      onClose={onClose}
      size="min(760px, 100vw)"
      title={
        data
          ? `${data.summary.customer_code} · ${data.summary.customer_name}`
          : code
      }
    >
      {detail.error ? (
        <LoadError error={detail.error} onRetry={detail.reload} />
      ) : !data ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <Steps
          detail={data}
          code={code}
          fiscalYear={fiscalYear}
          onChanged={changed}
        />
      )}
    </Drawer>
  );
}

function Steps({
  detail,
  code,
  fiscalYear,
  onChanged,
}: {
  detail: Detail;
  code: string;
  fiscalYear: number;
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const reason = hasScope(SCOPE.ack)
    ? null
    : "Ghi kết quả kiểm soát xuất khẩu cần quyền xác nhận tuân thủ (người phụ trách kiểm soát xuất khẩu).";
  const latest = (step: Step) =>
    detail.screenings.find((s) => s.step === step) ?? null;
  const [error, setError] = useState<unknown>(null);
  const download = async (file: ExportFile, name: string) => {
    try {
      saveBlob(await salesApi().exportControlFile(code, file), name);
      setError(null);
    } catch (failure) {
      setError(failure);
    }
  };
  const shared = { code, reason, onChanged, download };
  const needs = detail.summary.needs;

  return (
    <Flex vertical gap={12}>
      {needs.length ? (
        <Alert
          type="warning"
          showIcon
          title={`Còn phải làm: ${needs.map((n) => label(EXPORT_NEED, n)).join("; ")}.`}
        />
      ) : (
        <Alert type="success" showIcon title="Khách đã đủ các bước." />
      )}

      <Card size="small" title="1. Sàng lọc sản phẩm (PRV)">
        <Typography.Paragraph>
          Mã hàng khách mua (bảng quy đổi và đơn 12 tháng). Phân loại sửa ở Dữ
          liệu chủ › Mã hàng, cột “Phân loại xuất khẩu”.
        </Typography.Paragraph>
        <Table
          size="small"
          rowKey="prv_code"
          pagination={false}
          dataSource={detail.products}
          locale={{ emptyText: "Khách chưa có mã hàng nào." }}
          columns={[
            { title: "Mã PRV", dataIndex: "prv_code" },
            {
              title: "Phân loại",
              key: "class",
              render: (_, p) =>
                p.classification === null ? (
                  <StatusTag tone="unk">Chưa phân loại</StatusTag>
                ) : (
                  <StatusTag
                    tone={p.classification === "applicable" ? "warn" : "ok"}
                  >
                    {label(EXPORT_CLASSIFICATION, p.classification)}
                  </StatusTag>
                ),
            },
          ]}
        />
      </Card>

      <StepCard
        {...shared}
        step="denial_list"
        title="2. Danh sách cấm của tập đoàn"
        latest={latest("denial_list")}
        outcomes={["clear", "match"]}
        fileRequired={() => false}
      />

      <RedFlagCard
        {...shared}
        latest={latest("red_flag")}
        questions={detail.red_flags}
      />

      <StepCard
        {...shared}
        step="noc"
        title="4. NOEC gửi khách và NOC khách gửi lại"
        latest={latest("noc")}
        outcomes={["requested", "received"]}
        fileRequired={(outcome) => outcome === "received"}
        extra={
          <Button
            icon={<DownloadOutlined aria-hidden />}
            onClick={() => void download("noec-draft", `NOEC-${code}.eml`)}
            disabled={reason !== null}
          >
            Tải thư NOEC (nháp)
          </Button>
        }
      />

      <StepCard
        {...shared}
        step="esf"
        title={`5–6. ESF và gia hạn năm ${fiscalYear}`}
        latest={latest("esf")}
        outcomes={["approved"]}
        fileRequired={() => true}
        fiscalYear={fiscalYear}
        intro={
          <Typography.Paragraph>
            In phiếu ESF, trình ký lần lượt
            {detail.esf_approvers.length
              ? ` (${detail.esf_approvers.join(" → ")})`
              : ""}
            , quét bản đã ký rồi tải lên. Mỗi năm tài chính duyệt lại cho khách
            còn mua hàng
            {detail.summary.traded_recently
              ? "; khách này có mua trong 12 tháng."
              : "."}
          </Typography.Paragraph>
        }
        extra={
          <Flex wrap gap={8}>
            <Button
              icon={<DownloadOutlined aria-hidden />}
              onClick={() => void download("esf-form.xlsx", `ESF-${code}.xlsx`)}
            >
              Tải phiếu ESF (Excel)
            </Button>
            <Button
              icon={<DownloadOutlined aria-hidden />}
              onClick={() => void download("esf-form.pdf", `ESF-${code}.pdf`)}
            >
              Tải phiếu ESF (PDF)
            </Button>
          </Flex>
        }
      />

      {error ? (
        <Alert type="error" showIcon title={errorMessage(error)} />
      ) : null}
    </Flex>
  );
}

interface Shared {
  code: string;
  reason: string | null;
  onChanged: () => void;
  download: (file: ExportFile, name: string) => Promise<void>;
}

/** The step's latest result: what, when, who, and its document. */
function Latest({
  latest,
  code,
  download,
}: {
  latest: Screening | null;
  code: string;
  download: Shared["download"];
}) {
  const name = usePeople();
  if (!latest) return <StatusTag tone="unk">Chưa ghi kết quả</StatusTag>;
  return (
    <Flex wrap gap={8} align="center">
      <StatusTag
        tone={
          latest.outcome === "match" || latest.outcome === "escalated"
            ? "err"
            : latest.outcome === "requested"
              ? "warn"
              : "ok"
        }
      >
        {label(SCREENING_OUTCOME, `${latest.step}.${latest.outcome}`)}
        {latest.fiscal_year ? ` · năm ${latest.fiscal_year}` : ""}
      </StatusTag>
      <Typography.Text>
        Ngày {formatDate(latest.checked_on)}, {name(latest.recorded_by)} ghi lúc{" "}
        {formatDateTime(latest.recorded_at)}
      </Typography.Text>
      {latest.has_evidence ? (
        <Button
          size="small"
          icon={<DownloadOutlined aria-hidden />}
          onClick={() =>
            void download(`evidence/${latest.step}`, `${latest.step}-${code}`)
          }
        >
          Tải tài liệu
        </Button>
      ) : null}
      {latest.note ? (
        <Typography.Text>Ghi chú: {latest.note}</Typography.Text>
      ) : null}
    </Flex>
  );
}

interface StepValues {
  outcome: string;
  checked_on: ReturnType<typeof toPickerDay>;
  fiscal_year?: number;
  note?: string;
}

function StepCard({
  step,
  title,
  latest,
  outcomes,
  fileRequired,
  fiscalYear,
  intro,
  extra,
  code,
  reason,
  onChanged,
  download,
}: Shared & {
  step: Exclude<Step, "red_flag">;
  title: string;
  latest: Screening | null;
  outcomes: string[];
  fileRequired: (outcome: string) => boolean;
  fiscalYear?: number;
  intro?: ReactNode;
  extra?: ReactNode;
}) {
  const [form] = Form.useForm<StepValues>();
  const { run, pending } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<unknown>(null);
  const outcome = Form.useWatch("outcome", form) ?? outcomes[0]!;
  const needsFile = fileRequired(outcome);

  const submit = async (values: StepValues) => {
    if (needsFile && !file) {
      setError(new Error("Bước này cần tài liệu đã ký (PDF, JPG, PNG)."));
      return;
    }
    if (file && file.size > SCAN_MAX_BYTES) {
      setError(new Error("Tài liệu phải nhỏ hơn 10 MB."));
      return;
    }
    const body = {
      ...(step === "esf"
        ? { fiscal_year: values.fiscal_year ?? fiscalYear }
        : { outcome: values.outcome }),
      checked_on: fromPickerDay(values.checked_on) ?? "",
      note: values.note?.trim() || null,
      content_b64: file ? await base64(file) : null,
    };
    const result = await run(
      `screen/${code}/${step}`,
      { ...body, content_b64: file ? `${file.name}:${file.size}` : null },
      (key) =>
        salesApi().recordScreening(
          code,
          ROUTE[step],
          body as Parameters<ReturnType<typeof salesApi>["recordScreening"]>[2],
          key,
        ),
      "Đã ghi kết quả",
    );
    if (result.ok) {
      setError(null);
      setFile(null);
      form.resetFields(["note"]);
      onChanged();
    } else setError(result.error);
  };

  return (
    <Card size="small" title={title}>
      <Flex vertical gap={8}>
        {intro}
        <Latest latest={latest} code={code} download={download} />
        {extra}
        <Form<StepValues>
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          initialValues={{
            outcome: outcomes[0],
            checked_on: toPickerDay(lastDays(1, Date.now()).to),
            fiscal_year: fiscalYear,
          }}
          onFinish={submit}
        >
          <Flex wrap gap={12} align="start">
            {outcomes.length > 1 ? (
              <Form.Item name="outcome" label="Kết quả">
                <Segmented
                  aria-label={`Kết quả ${title}`}
                  options={outcomes.map((o) => ({
                    value: o,
                    label: label(SCREENING_OUTCOME, `${step}.${o}`),
                  }))}
                />
              </Form.Item>
            ) : null}
            <Form.Item
              name="checked_on"
              label={step === "esf" ? "Ngày duyệt" : "Ngày kiểm"}
              rules={[
                {
                  required: true,
                  message: "Cần ngày",
                  validateTrigger: "onSubmit",
                },
              ]}
            >
              <DatePicker format="DD/MM/YYYY" />
            </Form.Item>
            {step === "esf" ? (
              <Form.Item name="fiscal_year" label="Năm tài chính">
                <InputNumber min={2000} max={2100} />
              </Form.Item>
            ) : null}
          </Flex>
          <Form.Item name="note" label="Ghi chú">
            <Input.TextArea rows={2} maxLength={500} showCount />
          </Form.Item>
          <Flex wrap gap={8} align="center">
            <Upload
              accept={SCAN_ACCEPT}
              showUploadList={false}
              disabled={reason !== null}
              beforeUpload={(picked) => {
                setFile(picked);
                return false;
              }}
            >
              <Button
                icon={<UploadOutlined aria-hidden />}
                disabled={reason !== null}
              >
                {needsFile
                  ? "Chọn tài liệu đã ký"
                  : "Đính kèm tài liệu (không bắt buộc)"}
              </Button>
            </Upload>
            {file ? <Typography.Text>{file.name}</Typography.Text> : null}
            <GuardedButton
              reason={reason}
              type="primary"
              htmlType="submit"
              loading={pending === `screen/${code}/${step}`}
            >
              Ghi kết quả
            </GuardedButton>
          </Flex>
        </Form>
        {error ? (
          <Alert type="error" showIcon title={errorMessage(error)} />
        ) : null}
      </Flex>
    </Card>
  );
}

/** Step 3: every question answered yes or no; any yes is escalated. */
function RedFlagCard({
  latest,
  questions,
  code,
  reason,
  onChanged,
  download,
}: Shared & {
  latest: Screening | null;
  questions: SalesSchemas["RedFlagQuestionView"][];
}) {
  const { run, pending } = useAction();
  const [answers, setAnswers] = useState<Record<string, boolean>>(
    () => latest?.answers ?? {},
  );
  const [error, setError] = useState<unknown>(null);
  const unanswered = questions.filter((q) => answers[q.id] === undefined);
  const yes = questions.filter((q) => answers[q.id]).length;

  const submit = async () => {
    const body = {
      checked_on: lastDays(1, Date.now()).to,
      answers,
      note: null,
    };
    const result = await run(
      `screen/${code}/red_flag`,
      body,
      (key) => salesApi().recordScreening(code, "red-flag", body, key),
      yes ? "Đã ghi: có dấu hiệu, đã báo lên" : "Đã ghi: không có dấu hiệu",
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  return (
    <Card size="small" title="3. Câu hỏi red flag">
      <Flex vertical gap={8}>
        <Latest latest={latest} code={code} download={download} />
        {questions.map((q) => (
          <Flex key={q.id} wrap gap={8} align="center" justify="space-between">
            <Typography.Text className="max-w-xl">{q.text}</Typography.Text>
            {/* A Radio group, not Segmented: an unanswered question shows
                no answer, where Segmented always shows one selected. */}
            <Radio.Group
              aria-label={q.text}
              optionType="button"
              value={
                answers[q.id] === undefined
                  ? null
                  : answers[q.id]
                    ? "yes"
                    : "no"
              }
              disabled={reason !== null}
              onChange={(event) =>
                setAnswers((a) => ({
                  ...a,
                  [q.id]: event.target.value === "yes",
                }))
              }
              options={[
                { value: "no", label: "Không" },
                { value: "yes", label: "Có" },
              ]}
            />
          </Flex>
        ))}
        <Flex wrap gap={8} align="center">
          <GuardedButton
            reason={
              reason ??
              (unanswered.length
                ? `Còn ${unanswered.length} câu chưa trả lời.`
                : null)
            }
            type="primary"
            loading={pending === `screen/${code}/red_flag`}
            onClick={() => void submit()}
          >
            Ghi câu trả lời
          </GuardedButton>
          {yes ? (
            <Typography.Text>
              {yes} câu trả lời “Có”: khách sẽ được báo lên và đơn bị giữ.
            </Typography.Text>
          ) : null}
        </Flex>
        {error ? (
          <Alert type="error" showIcon title={errorMessage(error)} />
        ) : null}
      </Flex>
    </Card>
  );
}
