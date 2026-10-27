"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { Button, Space, Table, Typography } from "antd";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { usePeople } from "../_lib/people";
import {
  keyRows,
  RULE_KEY,
  RULE_LAYER,
  RULE_STATUS,
  type KeyRow,
  type RuleKey,
  type RuleVersion,
} from "../_lib/rules";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { ProposeDrawer } from "../_components/rule-editor";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { useAuth } from "../../../lib/auth/auth-context";
import { useFillHeight } from "../../../lib/use-fill-height";

const TONE: Record<RuleVersion["status"], "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};

/**
 * Quy tắc (tickets 19, 38, 36, 40): what applies to the company per key, the
 * platform's or its own, and every version it proposed. A holder of
 * `sales.rules.propose` (Sales phụ trách, Trưởng bộ phận Sales, or the
 * company's IT holding `sales_rules_editor`) proposes a whole document for
 * one key in a form drawn from that key's JSON Schema, reads what it changes
 * against the version in force, and sends it; the server validates it again
 * and opens a `sales.rules` platform approval, which someone who did not
 * propose it decides on `/approvals`. Nothing here decides. The server
 * answers this page only to holders of the scope, and lists only the keys the
 * caller may read: one holding prices or price policy is absent for someone
 * without `sales.price.read`, so the page draws the keys it is given and
 * names none of its own.
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

interface Proposing {
  key: RuleKey;
  /** The `StartOption.id` to open with; what applies now when absent. */
  start?: string;
}

function Rules() {
  const fill = useFillHeight();
  const seesApprovals = useAuth().hasScope("approvals.read");
  const name = usePeople();
  const rules = useResource(
    "sales/rules",
    useCallback(() => salesApi().rules(), []),
  );
  const [proposing, setProposing] = useState<Proposing | null>(null);

  const keys = rules.data ? keyRows(rules.data) : [];
  const versions = rules.data?.versions ?? [];
  const own = keys.filter((k) => k.layer === "tenant").length;
  const waiting = versions.filter((v) => v.status === "proposed").length;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Quy tắc")}
        title="Quy tắc của công ty"
        subtitle={`${own}/${keys.length} quy tắc đang dùng phiên bản riêng · ${waiting} phiên bản chờ duyệt. Người đề xuất không tự duyệt; ${seesApprovals ? "phiên bản được quyết trên trang Duyệt, mở từ liên kết ở mỗi phiên bản." : "người giữ quyền duyệt quy tắc quyết từng phiên bản."}`}
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
                    onClick={() => setProposing({ key: k.key })}
                    aria-label={`Đề xuất phiên bản mới: ${RULE_KEY[k.key]}`}
                  >
                    Đề xuất phiên bản mới
                  </Button>
                ),
              },
            ]}
          />
          <Typography.Title level={4} className="mb-0!">
            Các phiên bản của công ty
          </Typography.Title>
          <Table<RuleVersion>
            rowKey="version_id"
            loading={rules.loading}
            dataSource={versions}
            pagination={false}
            ref={fill.tableRef}
            scroll={{ x: "max-content", y: fill.y }}
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
                title: "Thao tác",
                key: "actions",
                fixed: "right",
                render: (_, v) => (
                  <Space orientation="vertical" size={2}>
                    {v.approval_id && seesApprovals ? (
                      <Link href={`/approvals/${v.approval_id}`}>
                        Mở yêu cầu duyệt
                      </Link>
                    ) : null}
                    <Button
                      size="small"
                      onClick={() =>
                        setProposing({
                          key: v.key,
                          start: `tenant:${v.version_id}`,
                        })
                      }
                      aria-label={`Dùng lại phiên bản này: ${v.ref}`}
                    >
                      Dùng lại phiên bản này
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </>
      )}
      {proposing && rules.data ? (
        <ProposeDrawer
          ruleKey={proposing.key}
          initialStart={proposing.start}
          view={rules.data}
          onClose={() => setProposing(null)}
          onProposed={() => {
            setProposing(null);
            rules.reload();
          }}
          onHeld={rules.reload}
        />
      ) : null}
    </div>
  );
}
