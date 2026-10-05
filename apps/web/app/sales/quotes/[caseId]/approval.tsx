"use client";

import { useState } from "react";
import {
  Alert,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { formatDate, formatDateTime } from "../../../../lib/dates";
import type { Currency } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { FINDING_CODE, label } from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { approvalReason } from "../../_lib/quote-actions";
import { useAction } from "../../_lib/use-action";
import { blobBase64, useLatestPdf } from "../../_components/artifacts-panel";
import { GuardedButton } from "../../_components/guarded-button";
import { PdfPage } from "../../_components/pdf-page";
import {
  FindingWords,
  Money,
  Quantity,
  UsdPerTonne,
} from "../../_components/money";

type Quote = SalesSchemas["QuoteCaseView"];

const PRICE_CODES = [
  "price_below_policy_floor",
  "price_floor_unknown",
  "price_basis_mismatch",
  "above_target_price",
];

/**
 * The approval pack beside the decision (Q9, V3Approvals re-cut): exactly
 * what is being approved (the document's hash, its number and validity, the
 * case version, who priced it, the decided terms and the price findings), so
 * the decision binds to what was seen. No typing ritual: a blocking price
 * finding needs its reason, nothing else does. The pricer is never the
 * approver; the button says so in words.
 */
export function ApprovalPanel({
  quote,
  viewer,
  onDone,
}: {
  quote: Quote;
  viewer: Viewer;
  onDone: () => void;
}) {
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [returning, setReturning] = useState(false);
  const [form] = Form.useForm<Record<string, string>>();
  const [returnForm] = Form.useForm<{ comment: string }>();
  const submission = quote.submission;
  const reason = approvalReason(quote, viewer);
  const preview = useLatestPdf(
    "quote",
    quote.case_id,
    quote.case_version,
    "quotation_preview",
  );
  const [pdf, setPdf] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const showPreview = async () => {
    if (!preview.artifact) return;
    setPreviewError(null);
    try {
      setPdf(
        await blobBase64(
          await salesApi().downloadArtifact(
            "quote",
            quote.case_id,
            preview.artifact.artifact_id,
          ),
        ),
      );
    } catch (failure) {
      setPreviewError(failure);
    }
  };
  const currency = quote.currency as Currency;
  if (!submission || !quote.pricing) return null;

  const priceFindings = quote.findings.filter((f) =>
    PRICE_CODES.includes(f.code),
  );
  const needReason = priceFindings.filter((f) => f.blocking);

  const approve = async (values: Record<string, string>) => {
    const body = {
      case_version: quote.case_version,
      decision: "approve" as const,
      document_sha256: submission.document_sha256,
      reasons: Object.fromEntries(
        needReason.map((f) => [f.key, (values[f.key] ?? "").trim()]),
      ),
    };
    const result = await run(
      "approve",
      body,
      (key) => salesApi().approval(quote.case_id, body, key),
      `Đã duyệt báo giá ${submission.quote_no}`,
    );
    if (result.ok) {
      setError(null);
      onDone();
    } else setError(result.error);
  };

  const sendBack = async ({ comment }: { comment: string }) => {
    const body = {
      case_version: quote.case_version,
      decision: "return" as const,
      comment: comment.trim(),
    };
    const result = await run(
      "return",
      body,
      (key) => salesApi().approval(quote.case_id, body, key),
      "Đã trả lại định giá",
    );
    if (result.ok) {
      setReturning(false);
      setError(null);
      onDone();
    } else setError(result.error);
  };

  return (
    <Card size="small" title={`Duyệt báo giá ${submission.quote_no}`}>
      <div className="space-y-3">
        <Descriptions
          size="small"
          bordered
          column={{ xs: 1, md: 2 }}
          items={[
            { key: "no", label: "Số báo giá", children: submission.quote_no },
            {
              key: "issued",
              label: "Ngày phát hành",
              children: formatDate(submission.issued_on),
            },
            {
              key: "valid",
              label: "Hiệu lực đến",
              children: formatDate(submission.valid_to),
            },
            {
              key: "to",
              label: "Gửi tới",
              children: submission.recipients.join(", ") || "Không rõ",
            },
            {
              key: "priced",
              label: "Người định giá",
              children: name(submission.priced_by),
            },
            {
              key: "submitted",
              label: "Trình lúc",
              children: `${formatDateTime(submission.submitted_at)} · ${name(submission.submitted_by)}`,
            },
            {
              key: "version",
              label: "Phiên bản hồ sơ",
              children: quote.case_version,
            },
            {
              key: "sha",
              label: "Mã băm tài liệu (SHA-256)",
              children: (
                <Typography.Text
                  code
                  copyable={{ text: submission.document_sha256 }}
                >
                  {submission.document_sha256.slice(0, 24)}…
                </Typography.Text>
              ),
            },
          ]}
        />
        <Typography.Title level={5}>Nội dung được trình</Typography.Title>
        <Table
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={quote.pricing.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Đơn giá",
              key: "p",
              align: "right",
              render: (_, l) => (
                <Money value={l.unit_price} currency={currency} />
              ),
            },
            {
              title: "MOQ",
              key: "m",
              align: "right",
              render: (_, l) => <Quantity value={l.moq} />,
            },
            {
              title: "Lead time",
              key: "lt",
              render: (_, l) => `${l.lead_time_days} ngày`,
            },
            {
              title: "Căn cứ đồng",
              key: "cu",
              render: (_, l) =>
                l.copper_basis.kind === "fixed" ? (
                  "Cố định"
                ) : (
                  <span>
                    <UsdPerTonne value={l.copper_basis.low_usd_per_tonne} /> –{" "}
                    <UsdPerTonne value={l.copper_basis.high_usd_per_tonne} />
                  </span>
                ),
            },
          ]}
        />
        <Typography.Title level={5}>Tài liệu báo giá</Typography.Title>
        {preview.artifact ? (
          pdf ? (
            <div className="max-w-3xl">
              <PdfPage data={pdf} page={1} boxes={[]} />
            </div>
          ) : (
            <GuardedButton
              reason={
                preview.artifact.downloadable
                  ? null
                  : "Bản xem trước chỉ người định giá và người duyệt mở được, khi báo giá đang chờ duyệt."
              }
              onClick={showPreview}
            >
              Xem bản xem trước (PDF, mã băm{" "}
              {preview.artifact.sha256.slice(0, 12)}…)
            </GuardedButton>
          )
        ) : (
          <Typography.Paragraph role="note">
            Chưa có bản xem trước ở phiên bản {quote.case_version}. Soạn “Tài
            liệu báo giá (bản xem trước)” ở mục Tệp và thư nháp bên dưới để xem
            tài liệu trước khi duyệt.
          </Typography.Paragraph>
        )}
        <ActionError error={previewError} />
        <Alert
          type="info"
          showIcon
          title="Bản ký giấy vẫn là bản duyệt chính thức cho tới khi Proterial quyết định; duyệt trên cổng là đề xuất."
        />
        <Form
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          onFinish={approve}
        >
          {priceFindings.length ? (
            <div className="space-y-2">
              <Typography.Title level={5}>Cờ về giá</Typography.Title>
              {priceFindings.map((f) => (
                <Card key={f.key} size="small" type="inner">
                  <Typography.Text strong>
                    {label(FINDING_CODE, f.code)}
                    {f.line_no ? ` · dòng ${f.line_no}` : ""}
                  </Typography.Text>
                  <Descriptions
                    size="small"
                    column={{ xs: 1, md: 2 }}
                    items={[
                      {
                        key: "e",
                        label: "Mong đợi",
                        children: <FindingWords value={f.expected} />,
                      },
                      {
                        key: "a",
                        label: "Giá quyết định",
                        children: <FindingWords value={f.actual} />,
                      },
                    ]}
                  />
                  {f.blocking ? (
                    <Form.Item
                      name={f.key}
                      label="Lý do chấp nhận khi duyệt"
                      rules={[
                        {
                          required: true,
                          message: "Cờ chặn cần lý do",
                          validateTrigger: "onSubmit",
                        },
                      ]}
                    >
                      <Input.TextArea
                        rows={2}
                        maxLength={1000}
                        disabled={reason !== null}
                      />
                    </Form.Item>
                  ) : (
                    <Typography.Text>
                      Duyệt báo giá là ghi nhận cờ này.
                    </Typography.Text>
                  )}
                </Card>
              ))}
            </div>
          ) : (
            <Typography.Paragraph>Không có cờ nào về giá.</Typography.Paragraph>
          )}
          <Space wrap align="start" className="mt-2">
            <GuardedButton
              type="primary"
              htmlType="submit"
              reason={reason}
              loading={pending === "approve"}
            >
              Duyệt báo giá
            </GuardedButton>
            <GuardedButton
              reason={reason}
              inlineReason={false}
              onClick={() => setReturning(true)}
            >
              Trả lại định giá
            </GuardedButton>
          </Space>
        </Form>
        <ActionError error={error} />
      </div>
      <Modal
        open={returning}
        title="Trả lại định giá"
        okText="Trả lại"
        cancelText="Hủy"
        okButtonProps={{ danger: true, loading: pending === "return" }}
        onCancel={() => setReturning(false)}
        onOk={() => returnForm.submit()}
        destroyOnHidden
      >
        <Form
          form={returnForm}
          layout="vertical"
          validateTrigger="onBlur"
          onFinish={sendBack}
        >
          <Form.Item
            name="comment"
            label="Lý do trả lại"
            rules={[
              {
                required: true,
                message: "Lý do là bắt buộc",
                validateTrigger: "onSubmit",
              },
            ]}
          >
            <Input.TextArea rows={3} maxLength={1000} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

/** For a page that only lists: who priced it, in a sentence. */
export function pricedBy(
  quote: Quote,
  name: (id: string | null | undefined) => string,
): string {
  return quote.pricing
    ? `${name(quote.pricing.decided_by)} · ${formatDateTime(quote.pricing.decided_at)}`
    : "Chưa định giá";
}
