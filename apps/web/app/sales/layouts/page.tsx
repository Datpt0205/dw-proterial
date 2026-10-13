"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import {
  Descriptions,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { approvalClient } from "../../../lib/approvals/registry";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { LAYOUT_FIELDS, LAYOUT_STATUS } from "../_lib/layouts";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

type Layout = SalesSchemas["LayoutView"];

const TONE: Record<string, "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};

/**
 * Mẫu PO (ticket 30): the customers' forms people mapped, and the decision on
 * each. A PIC maps a form from a message in the inbox; Trưởng bộ phận Sales,
 * who did not map it, decides it here on the platform approval the proposal
 * opened (`sales.layout`, `POST /approvals/{id}/decisions`, dw_sales ADR
 * 0004): stamped with `sales.layout.approve`, refused to the person who
 * mapped it (tách nhiệm), and with a written comment either way. The worker
 * then applies the decision to the layout. An approved form is how DW1 reads
 * that customer's later POs, with no model.
 */
export default function LayoutsPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Layouts />
      </Suspense>
    </ScopeGate>
  );
}

function Layouts() {
  const { principalId, hasScope } = useAuth();
  const name = usePeople();
  const layouts = useResource(
    "sales/layouts",
    useCallback(() => salesApi().layouts(), []),
  );
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [deciding, setDeciding] = useState<{
    layout: Layout;
    approve: boolean;
  } | null>(null);
  const [form] = Form.useForm<{ comment: string }>();

  const reason = (layout: Layout) =>
    !hasScope(SCOPE.layoutApprove)
      ? "Chỉ Trưởng bộ phận Sales duyệt mẫu PO."
      : layout.proposed_by === principalId
        ? "Bạn đã lập mẫu này nên không tự duyệt được (tách nhiệm)."
        : null;

  // The decision binds to the version this screen showed; the worker applies
  // it to the layout once it is recorded, so the row changes a moment later.
  const decide = async (layout: Layout, approve: boolean, comment: string) => {
    const sent = { approve, comment, subject_version: layout.version };
    const result = await run(
      `decide/${layout.layout_id}`,
      sent,
      (key) =>
        approvalClient("sales.layout").decideApproval(
          layout.approval_id,
          sent,
          key,
        ),
      `Đã ghi quyết định ${approve ? "duyệt" : "từ chối"} mẫu PO của ${layout.customer_code}; trạng thái mẫu đổi khi DW1 áp dụng quyết định.`,
    );
    if (result.ok) {
      setError(null);
      setDeciding(null);
      layouts.reload();
    } else setError(result.error);
  };

  const rows = layouts.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Mẫu PO")}
        title="Mẫu PO của khách"
        subtitle={`${rows.filter((l) => l.status === "proposed").length} mẫu chờ duyệt · ${rows.filter((l) => l.status === "approved").length} đã duyệt. Người lập mẫu không tự duyệt; DW1 đọc PO sau của khách theo mẫu đã duyệt, không dùng mô hình.`}
      />
      <ActionError error={error} />
      {layouts.error ? (
        <LoadError error={layouts.error} onRetry={layouts.reload} />
      ) : (
        <Table<Layout>
          rowKey="layout_id"
          loading={layouts.loading}
          dataSource={rows}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: layouts.loading
              ? " "
              : "Chưa có mẫu PO nào. Lập mẫu từ một thư trong Hộp thư có PO DW1 chưa đọc được.",
          }}
          footer={() => `${rows.length} mẫu`}
          expandable={{
            expandedRowRender: (layout) => <MappingDetail layout={layout} />,
          }}
          columns={[
            {
              title: "Khách",
              key: "customer",
              render: (_, l) => (
                <span className="flex flex-col">
                  <Typography.Text strong>{l.customer_code}</Typography.Text>
                  <Typography.Text>
                    {l.kind === "pdf" ? "PDF" : "Excel"} · phiên bản {l.version}
                  </Typography.Text>
                </span>
              ),
            },
            {
              title: "Trạng thái",
              key: "status",
              render: (_, l) => (
                <StatusTag tone={TONE[l.status] ?? "unk"}>
                  {LAYOUT_STATUS[l.status] ?? l.status}
                </StatusTag>
              ),
            },
            {
              title: "Lập từ",
              key: "sample",
              render: (_, l) => (
                <span className="flex flex-col">
                  <Link
                    href={`/sales/inbox?message=${encodeURIComponent(l.sample.message_id)}`}
                  >
                    Thư {l.sample.message_id}
                  </Link>
                  {l.prefill?.outcome === "proposed" ? (
                    <StatusTag tone="warn">
                      Bắt đầu từ gợi ý của mô hình
                    </StatusTag>
                  ) : null}
                </span>
              ),
            },
            {
              title: `Người lập (${TIME_ZONE_LABEL})`,
              key: "proposed",
              render: (_, l) => (
                <span className="flex flex-col">
                  <span>{name(l.proposed_by)}</span>
                  <Typography.Text type="secondary">
                    {formatDateTime(l.proposed_at, { zoneLabel: false })}
                  </Typography.Text>
                </span>
              ),
            },
            {
              title: "Người quyết định",
              key: "decided",
              render: (_, l) =>
                l.decided_by ? <span>{name(l.decided_by)}</span> : "",
            },
            {
              title: "Quyết định",
              key: "decide",
              fixed: "right",
              render: (_, l) =>
                l.status === "proposed" ? (
                  <Space>
                    <GuardedButton
                      size="small"
                      type="primary"
                      inlineReason={false}
                      reason={reason(l)}
                      onClick={() => setDeciding({ layout: l, approve: true })}
                    >
                      Duyệt
                    </GuardedButton>
                    <GuardedButton
                      size="small"
                      danger
                      inlineReason={false}
                      reason={reason(l)}
                      onClick={() => setDeciding({ layout: l, approve: false })}
                    >
                      Từ chối
                    </GuardedButton>
                  </Space>
                ) : null,
            },
          ]}
        />
      )}
      <Modal
        open={deciding !== null}
        title={`${deciding?.approve ? "Duyệt" : "Từ chối"} mẫu PO của ${deciding?.layout.customer_code ?? ""}`}
        okText={deciding?.approve ? "Duyệt mẫu" : "Từ chối mẫu"}
        cancelText="Hủy"
        okButtonProps={{
          danger: deciding?.approve === false,
          loading:
            deciding !== null &&
            pending === `decide/${deciding.layout.layout_id}`,
        }}
        onCancel={() => setDeciding(null)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={({ comment }) =>
            deciding &&
            decide(deciding.layout, deciding.approve, comment.trim())
          }
        >
          <Form.Item
            name="comment"
            label="Nhận xét"
            extra="Bắt buộc với mọi quyết định của Sales; lưu trên yêu cầu duyệt."
            rules={[
              {
                required: true,
                whitespace: true,
                message: "Nhận xét là bắt buộc",
              },
            ]}
          >
            <Input.TextArea rows={3} maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function MappingDetail({ layout }: { layout: Layout }) {
  const mapping = layout.mapping;
  return (
    <Descriptions
      size="small"
      bordered
      column={{ xs: 1, md: 2 }}
      items={[
        ...LAYOUT_FIELDS.filter((f) => mapping[f.field] !== undefined).map(
          ({ field, label }) => ({
            key: field,
            label,
            children: mapping[field] ?? "Mẫu không in",
          }),
        ),
        ...(layout.kind === "pdf"
          ? [
              {
                key: "numbers",
                label: "Số và ngày",
                children: `nhóm nghìn "${mapping.thousands_separator}", thập phân "${mapping.decimal_separator}", ngày ${mapping.date_format}`,
              },
            ]
          : []),
      ]}
    />
  );
}
