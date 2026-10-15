"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  Space,
  Table,
  Typography,
} from "antd";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import {
  keyRows,
  parseDocument,
  RULE_KEY,
  RULE_LAYER,
  RULE_STATUS,
  startingDocument,
  type KeyRow,
  type RuleKey,
  type RuleVersion,
} from "../_lib/rules";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

const TONE: Record<RuleVersion["status"], "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};

/**
 * Quy tắc (tickets 19, 38, 36): what applies to the company per key, the
 * platform's or its own, and every version it proposed. A holder of
 * `sales.rules.propose` (Sales phụ trách or Trưởng bộ phận Sales) proposes a
 * whole document for one key; the server validates it against that key's
 * schema and opens a `sales.rules` platform approval, which someone who did
 * not propose it decides on `/approvals` with a comment. Nothing here
 * decides. The server answers this page only to holders of the scope (the
 * documents can hold price rules), and refuses a proposal from anyone else.
 */
export default function RulesPage() {
  return (
    <ScopeGate scope={SCOPE.rulesPropose}>
      <Suspense>
        <Rules />
      </Suspense>
    </ScopeGate>
  );
}

function Rules() {
  const name = usePeople();
  const rules = useResource(
    "sales/rules",
    useCallback(() => salesApi().rules(), []),
  );
  const [proposing, setProposing] = useState<RuleKey | null>(null);

  const keys = rules.data ? keyRows(rules.data) : [];
  const versions = rules.data?.versions ?? [];
  const own = keys.filter((k) => k.layer === "tenant").length;
  const waiting = versions.filter((v) => v.status === "proposed").length;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Quy tắc")}
        title="Quy tắc của công ty"
        subtitle={`${own}/${keys.length} quy tắc đang dùng phiên bản riêng · ${waiting} phiên bản chờ duyệt. Người đề xuất không tự duyệt; phiên bản được quyết trên trang Duyệt, mở từ liên kết ở mỗi phiên bản.`}
      />
      {rules.error ? (
        <LoadError error={rules.error} onRetry={rules.reload} />
      ) : (
        <>
          <Table<KeyRow>
            rowKey="key"
            loading={rules.loading}
            dataSource={keys}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{ emptyText: rules.loading ? " " : "Không có quy tắc." }}
            footer={() => `${keys.length} quy tắc`}
            columns={[
              {
                title: "Quy tắc",
                key: "key",
                render: (_, k) => (
                  <span className="flex flex-col">
                    <Typography.Text strong>{RULE_KEY[k.key]}</Typography.Text>
                    <Typography.Text code>{k.key}</Typography.Text>
                  </span>
                ),
              },
              {
                title: "Đang áp dụng",
                key: "in_force",
                render: (_, k) => (
                  <Space orientation="vertical" size={2}>
                    <Typography.Text code>{k.inForce}</Typography.Text>
                    <StatusTag tone={k.layer === "tenant" ? "ok" : "gray"}>
                      {RULE_LAYER[k.layer]}
                    </StatusTag>
                  </Space>
                ),
              },
              {
                title: "Bản của nền tảng",
                key: "platform",
                render: (_, k) => (
                  <Typography.Text code>{k.platform}</Typography.Text>
                ),
              },
              {
                title: "Chờ duyệt",
                key: "waiting",
                align: "right",
                render: (_, k) => k.waiting,
              },
              {
                title: "Đề xuất",
                key: "propose",
                fixed: "right",
                render: (_, k) => (
                  <Button
                    size="small"
                    onClick={() => setProposing(k.key)}
                    aria-label={`Đề xuất phiên bản mới: ${RULE_KEY[k.key]}`}
                  >
                    Đề xuất phiên bản mới
                  </Button>
                ),
              },
            ]}
          />
          <Typography.Title level={4} className="!mb-0">
            Các phiên bản của công ty
          </Typography.Title>
          <Table<RuleVersion>
            rowKey="version_id"
            loading={rules.loading}
            dataSource={versions}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: rules.loading
                ? " "
                : "Công ty chưa có phiên bản riêng nào: mọi quy tắc đang theo bản của nền tảng.",
            }}
            footer={() => `${versions.length} phiên bản`}
            expandable={{
              expandedRowRender: (v) => (
                <pre
                  aria-label={`Tài liệu ${v.ref}`}
                  className="m-0 max-h-96 overflow-auto whitespace-pre-wrap"
                >
                  {JSON.stringify(v.document, null, 2)}
                </pre>
              ),
            }}
            columns={[
              {
                title: "Phiên bản",
                key: "ref",
                render: (_, v) => (
                  <span className="flex flex-col">
                    <Typography.Text strong>{RULE_KEY[v.key]}</Typography.Text>
                    <Typography.Text code>{v.ref}</Typography.Text>
                  </span>
                ),
              },
              {
                title: "Trạng thái",
                key: "status",
                render: (_, v) => (
                  <StatusTag tone={TONE[v.status]}>
                    {RULE_STATUS[v.status]}
                  </StatusTag>
                ),
              },
              {
                title: `Người đề xuất (${TIME_ZONE_LABEL})`,
                key: "proposed",
                render: (_, v) => (
                  <span className="flex flex-col">
                    <span>{name(v.proposed_by)}</span>
                    <span>
                      {formatDateTime(v.proposed_at, { zoneLabel: false })}
                    </span>
                  </span>
                ),
              },
              {
                title: `Người quyết định (${TIME_ZONE_LABEL})`,
                key: "decided",
                render: (_, v) =>
                  v.decided_by ? (
                    <span className="flex flex-col">
                      <span>{name(v.decided_by)}</span>
                      <span>
                        {formatDateTime(v.decided_at, { zoneLabel: false })}
                      </span>
                      {v.comment ? <span>{v.comment}</span> : null}
                    </span>
                  ) : (
                    ""
                  ),
              },
              {
                title: "Yêu cầu duyệt",
                key: "approval",
                fixed: "right",
                render: (_, v) =>
                  v.approval_id ? (
                    <Link href={`/approvals/${v.approval_id}`}>
                      Mở yêu cầu duyệt
                    </Link>
                  ) : (
                    ""
                  ),
              },
            ]}
          />
        </>
      )}
      {proposing && rules.data ? (
        <ProposeDrawer
          ruleKey={proposing}
          start={startingDocument(rules.data, proposing)}
          onClose={() => setProposing(null)}
          onProposed={() => {
            setProposing(null);
            rules.reload();
          }}
        />
      ) : null}
    </div>
  );
}

function ProposeDrawer({
  ruleKey,
  start,
  onClose,
  onProposed,
}: {
  ruleKey: RuleKey;
  start: ReturnType<typeof startingDocument>;
  onClose: () => void;
  onProposed: () => void;
}) {
  const { modal } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [form] = Form.useForm<{ text: string }>();
  const id = `propose/${ruleKey}`;

  const propose = async (text: string) => {
    const parsed = parseDocument(text);
    if (!parsed.ok) return;
    const body = { document: parsed.document };
    const result = await run(
      id,
      { ruleKey, ...body },
      (key) => salesApi().proposeRule(ruleKey, body, key),
      `Đã gửi duyệt phiên bản mới của "${RULE_KEY[ruleKey]}". Người khác duyệt trên trang Duyệt.`,
    );
    if (result.ok) onProposed();
    else setError(result.error);
  };

  // Closing with an edited document asks first (ui-quality §9).
  const close = () => {
    if (!form.isFieldsTouched()) return onClose();
    modal.confirm({
      title: "Bỏ tài liệu đang sửa?",
      content: "Những thay đổi chưa gửi duyệt sẽ mất.",
      okText: "Bỏ thay đổi",
      okButtonProps: { danger: true },
      cancelText: "Tiếp tục sửa",
      autoFocusButton: "cancel",
      onOk: onClose,
    });
  };

  return (
    <Drawer
      open
      onClose={close}
      size="min(720px, 100vw)"
      title={`Đề xuất phiên bản mới: ${RULE_KEY[ruleKey]}`}
      destroyOnHidden
      footer={
        <Space>
          <Button
            type="primary"
            loading={pending === id}
            onClick={() => form.submit()}
          >
            Gửi duyệt
          </Button>
          <Button onClick={close}>Hủy</Button>
        </Space>
      }
    >
      <Typography.Paragraph>
        Gửi toàn bộ tài liệu của quy tắc, kèm số phiên bản mới: máy chủ kiểm tài
        liệu theo lược đồ của quy tắc, và từ chối số phiên bản nền tảng đã dùng.{" "}
        {start
          ? start.inForce
            ? "Ô dưới mở sẵn phiên bản công ty đang áp dụng."
            : "Ô dưới mở sẵn phiên bản gần nhất của công ty."
          : "Công ty chưa có phiên bản riêng của quy tắc này, và tài liệu của nền tảng không gửi tới trang này: hãy dán toàn bộ tài liệu."}
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={{
          text: start ? JSON.stringify(start.document, null, 2) : "",
        }}
        onFinish={({ text }) => propose(text)}
      >
        <Form.Item
          name="text"
          label="Tài liệu (JSON)"
          rules={[
            {
              validator: async (_, text: string | undefined) => {
                const parsed = parseDocument(text ?? "");
                if (!parsed.ok) throw new Error(parsed.error);
              },
            },
          ]}
        >
          <Input.TextArea rows={18} spellCheck={false} />
        </Form.Item>
      </Form>
      <ActionError error={error} />
    </Drawer>
  );
}
