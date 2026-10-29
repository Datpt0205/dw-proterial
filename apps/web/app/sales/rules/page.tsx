"use client";

import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { Button, Collapse, Space, Table, Typography } from "antd";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { usePeople } from "../_lib/people";
import {
  ADVANCED_RULES,
  keyRows,
  RULE_ABOUT,
  RULE_KEY,
  RULE_LAYER,
  RULE_STATUS,
  type KeyRow,
  type RuleKey,
  type RuleVersion,
} from "../_lib/rules";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import {
  useIsPhone,
  usePhoneColumns,
  usePhoneTable,
} from "../_components/list-parts";
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
 * `sales.rules.propose` (Trưởng bộ phận Sales, or the company's admin holding
 * `sales_rules_editor`; a PIC holds none since 2026-10-28) writes a whole
 * document for one key in a form drawn from that key's JSON Schema, reads
 * what it changes against the version in force, and sends it; the server
 * validates it again. The head's version applies at once; anyone else's
 * opens a `sales.rules` platform approval the head decides on `/approvals`.
 * Nothing here decides. The server
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
  const { hasScope } = useAuth();
  const seesApprovals = hasScope("approvals.read");
  // The head's own version applies at once (2026-10-28); the server decides.
  const appliesAtOnce = hasScope(SCOPE.rulesApprove);
  const name = usePeople();
  const phone = usePhoneColumns();
  const table = usePhoneTable();
  const isPhone = useIsPhone();
  const rules = useResource(
    "sales/rules",
    useCallback(() => salesApi().rules(), []),
  );
  const [proposing, setProposing] = useState<Proposing | null>(null);

  const keys = rules.data ? keyRows(rules.data) : [];
  const main = keys.filter((k) => !ADVANCED_RULES.has(k.key));
  const advanced = keys.filter((k) => ADVANCED_RULES.has(k.key));

  // One table per group of keys: what each rule decides, whose version
  // applies, what waits, and the way in. Version codes stay in the editor.
  const keyTable = (rows: KeyRow[], loading: boolean) => (
    <Table<KeyRow>
      rowKey="key"
      loading={loading}
      dataSource={rows}
      pagination={false}
      scroll={table.scroll()}
      locale={{ emptyText: loading ? " " : "Không có quy tắc." }}
      tableLayout={table.tableLayout}
      columns={phone(
        [
          {
            title: "Quy tắc",
            key: "key",
            render: (_, k) => (
              <span className="flex flex-col">
                <Typography.Text strong>{RULE_KEY[k.key]}</Typography.Text>
                <Typography.Text>{RULE_ABOUT[k.key]}</Typography.Text>
                {isPhone ? (
                  <span className="mt-1 flex flex-wrap items-center gap-2">
                    <StatusTag tone={k.layer === "tenant" ? "ok" : "gray"}>
                      {RULE_LAYER[k.layer]}
                    </StatusTag>
                    {k.waiting ? (
                      <Typography.Text>{k.waiting} chờ duyệt</Typography.Text>
                    ) : null}
                  </span>
                ) : null}
              </span>
            ),
          },
          {
            title: "Đang dùng",
            key: "in_force",
            render: (_, k) => (
              <StatusTag tone={k.layer === "tenant" ? "ok" : "gray"}>
                {RULE_LAYER[k.layer]}
              </StatusTag>
            ),
          },
          {
            title: "Chờ duyệt",
            key: "waiting",
            align: "right",
            render: (_, k) => k.waiting,
          },
          {
            title: appliesAtOnce ? "Sửa" : "Đề xuất",
            key: "propose",
            fixed: "right",
            render: (_, k) => (
              <Button
                size="small"
                onClick={() => setProposing({ key: k.key })}
                aria-label={`${appliesAtOnce ? "Sửa quy tắc" : "Đề xuất phiên bản mới"}: ${RULE_KEY[k.key]}`}
              >
                {appliesAtOnce ? "Sửa quy tắc" : "Đề xuất bản mới"}
              </Button>
            ),
          },
        ],
        ["propose"],
      )}
    />
  );
  const versions = rules.data?.versions ?? [];
  const own = keys.filter((k) => k.layer === "tenant").length;
  const waiting = versions.filter((v) => v.status === "proposed").length;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Quy tắc")}
        title="Quy tắc của công ty"
        subtitle={`${own}/${keys.length} quy tắc đang dùng phiên bản riêng · ${waiting} phiên bản chờ duyệt. ${appliesAtOnce ? "Bản bạn sửa được áp dụng ngay; bản người khác đề xuất chờ bạn duyệt trên trang Duyệt." : `Người đề xuất không tự duyệt; ${seesApprovals ? "phiên bản được quyết trên trang Duyệt, mở từ liên kết ở mỗi phiên bản." : "Trưởng bộ phận Sales quyết từng phiên bản."}`}`}
      />
      {rules.error ? (
        <LoadError error={rules.error} onRetry={rules.reload} />
      ) : (
        <>
          {keyTable(main, rules.loading)}
          <Collapse
            items={[
              {
                key: "advanced",
                label: `Nâng cao (${advanced.length} quy tắc): KPI, chữ trên tài liệu, mẫu nhập Bravo, thư chuyển PC/QA`,
                children: keyTable(advanced, rules.loading),
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
            scroll={table.scroll(fill.y)}
            tableLayout={table.tableLayout}
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
            columns={phone(
              [
                {
                  title: "Phiên bản",
                  key: "ref",
                  render: (_, v) => (
                    <span className="flex flex-col">
                      <Typography.Text strong>
                        {RULE_KEY[v.key]}
                      </Typography.Text>
                      <Typography.Text code>{v.ref}</Typography.Text>
                    </span>
                  ),
                },
                {
                  title: "Trạng thái",
                  key: "status",
                  render: (_, v) => (
                    <StatusTag tone={TONE[v.status]}>
                      {v.applied_directly && v.status === "approved"
                        ? "Trưởng bộ phận áp dụng trực tiếp"
                        : RULE_STATUS[v.status]}
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
                        Dùng lại
                      </Button>
                    </Space>
                  ),
                },
              ],
              ["status", "actions"],
            )}
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
