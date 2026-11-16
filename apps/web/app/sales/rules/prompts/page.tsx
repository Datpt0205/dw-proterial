"use client";

import { Suspense, useCallback } from "react";
import Link from "next/link";
import { Table, Typography } from "antd";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { useAuth } from "../../../../lib/auth/auth-context";
import { formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { usePeople } from "../../_lib/people";
import { RULE_STATUS } from "../../_lib/rules";
import { SKILL_LAYER } from "../../_lib/skills";
import {
  scoreLine,
  securityLine,
  type PromptVersion,
  type PromptsView,
} from "../../_lib/prompts";
import { useResource } from "../../_lib/use-resource";
import { salesCrumbs } from "../../_components/crumbs";
import { usePhoneColumns, usePhoneTable } from "../../_components/list-parts";
import { PromptChanges, PromptLines } from "../../_components/prompt-changes";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";

const TONE: Record<PromptVersion["status"], "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};

/**
 * Lời nhắc DW1 học (ticket 43, dw_sales ADR 0015 decision 5): the
 * description reading's prompt as the company holds it, and every version
 * DW1's optimiser proposed from the lines people decided, each opened to
 * show what it changes against the version in force, its replay and the
 * decided lines it came from. Read by whoever decides them
 * (`sales.rules.approve`); each is decided on its `sales.prompts` approval on
 * `/approvals`, never here and never by its proposer. Nothing here decides.
 */
export default function PromptsPage() {
  return (
    <ScopeGate scope={SCOPE.rulesApprove}>
      <Suspense>
        <Prompts />
      </Suspense>
    </ScopeGate>
  );
}

function Prompts() {
  const { hasScope } = useAuth();
  const seesApprovals = hasScope("approvals.read");
  const name = usePeople();
  const phone = usePhoneColumns();
  const table = usePhoneTable();
  const prompts = useResource(
    "sales/prompts",
    useCallback(() => salesApi().prompts(), []),
  );
  const view: PromptsView | null = prompts.data;
  const versions = view?.versions ?? [];
  const waiting = versions.filter((v) => v.status === "proposed").length;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs(
          { title: "Quy tắc", href: "/sales/rules" },
          "Lời nhắc DW1 học",
        )}
        title="Lời nhắc DW1 học"
        subtitle={
          view
            ? `Đang dùng ${view.in_force} (${SKILL_LAYER[view.layer].toLowerCase()}, ${view.demonstrations.length} dòng mẫu) · ${waiting} phiên bản chờ duyệt`
            : undefined
        }
        help="DW1 học từ các dòng người đã quyết: nó thử thêm vài dòng mẫu vào lời nhắc đọc mô tả hàng, chạy lại trên mọi dòng đã quyết và các ca bảo mật, và chỉ đề xuất khi không dòng nào đọc kém đi. Trưởng bộ phận duyệt trên trang Duyệt; DW1 không tự áp dụng. Lời nhắc chỉ là lời: không thêm công cụ, quyền hay con số nào."
      />
      {prompts.error ? (
        <LoadError error={prompts.error} onRetry={prompts.reload} />
      ) : (
        <Table<PromptVersion>
          rowKey="version_id"
          loading={prompts.loading}
          dataSource={versions}
          pagination={false}
          scroll={table.scroll()}
          tableLayout={table.tableLayout}
          locale={{
            emptyText: prompts.loading
              ? " "
              : "DW1 chưa đề xuất phiên bản nào: cần đủ dòng người đã quyết mới thử.",
          }}
          footer={() => `${versions.length} phiên bản`}
          expandable={{
            expandedRowRender: (v) =>
              view && v.status === "proposed" ? (
                <PromptChanges view={view} version={v} />
              ) : (
                <PromptLines version={v} />
              ),
          }}
          columns={phone(
            [
              {
                title: "Phiên bản",
                key: "ref",
                render: (_, v) => (
                  <span className="flex flex-col">
                    <Typography.Text code>{v.ref}</Typography.Text>
                    <Typography.Text>
                      DW1 đề xuất {formatDateTime(v.proposed_at)}
                    </Typography.Text>
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
                title: "Chạy lại trên dòng đã quyết",
                key: "replay",
                render: (_, v) =>
                  v.replay ? (
                    <span className="flex flex-col">
                      <Typography.Text>{scoreLine(v.replay)}</Typography.Text>
                      <Typography.Text>
                        {securityLine(v.replay)}
                      </Typography.Text>
                    </span>
                  ) : null,
              },
              {
                title: "Người quyết định",
                key: "decided_by",
                render: (_, v) =>
                  v.decided_by ? (
                    <span className="flex flex-col">
                      <span>{name(v.decided_by)}</span>
                      {v.comment ? (
                        <Typography.Text
                          ellipsis={{ tooltip: v.comment }}
                          className="max-w-xs"
                        >
                          {v.comment}
                        </Typography.Text>
                      ) : null}
                    </span>
                  ) : null,
              },
              {
                title: "Thao tác",
                key: "actions",
                fixed: "right",
                render: (_, v) =>
                  v.approval_id && seesApprovals && v.status === "proposed" ? (
                    <Link href={`/approvals/${v.approval_id}`}>
                      Mở phê duyệt
                    </Link>
                  ) : null,
              },
            ],
            ["status", "actions"],
          )}
        />
      )}
    </div>
  );
}
