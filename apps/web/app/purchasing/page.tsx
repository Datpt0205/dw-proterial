"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { Button, Card, Empty, Flex, Skeleton, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { Approval, PurchaseCase } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../components/load-error";
import { formatDateTime } from "../../lib/dates";
import { useAuth } from "../../lib/auth/auth-context";
import { apiClient } from "../../lib/session";
import { useCachedResource } from "../../lib/use-cached-resource";
import { purchasingApi } from "./_lib/api";
import { casePage } from "./_lib/cases";
import { money } from "./_lib/format";
import { FINDING } from "./_lib/labels";
import { SCOPE } from "./_lib/scopes";
import { DecideApproval } from "./_components/decide-approval";
import { Rows } from "./_components/rows";
import { purchasingCrumbs, ScopeGate } from "./_components/frame";
import { CaseStatusTag, MarkTag } from "./_components/tags";

/**
 * "Việc của tôi": what DW2 is waiting on this person for, the decisions
 * first. An approval is decided here with one press after its reason, the
 * request it decides shown beside it (number, amount, findings, tier) so the
 * decision binds to what was seen. Work on a case opens the case. A
 * requester sees their own requests and where each stands.
 */
export default function MyWorkPage() {
  return (
    <ScopeGate scope={[SCOPE.read, SCOPE.readOwn, SCOPE.approveLast]}>
      <MyWork />
    </ScopeGate>
  );
}

const CASE_APPROVALS = new Set(["purchasing.request", "purchasing.reapproval"]);

function MyWork() {
  const { hasScope } = useAuth();
  const decides = hasScope(SCOPE.decide);
  const staff = hasScope(SCOPE.read);
  const approvals = useCachedResource<Approval[]>(
    `purchasing/approvals:${decides}`,
    useCallback(
      async () =>
        decides
          ? (await apiClient().listApprovals({ limit: 100 })).items.filter(
              (a) =>
                a.approval_type.startsWith("purchasing.") &&
                a.status === "pending" &&
                a.can_decide,
            )
          : [],
      [decides],
    ),
  );
  // A director who only decides the last tier reads no list: each request
  // they decide is read through its approval below.
  const lists = staff || hasScope(SCOPE.readOwn);
  const cases = useCachedResource(
    `purchasing/requests:first:${lists}`,
    useCallback(
      () =>
        lists
          ? casePage(null)
          : Promise.resolve({ items: [], next_cursor: null }),
      [lists],
    ),
  );
  const mail = useCachedResource(
    `purchasing/mail:${staff}`,
    useCallback(
      () => (staff ? purchasingApi().mailbox() : Promise.resolve([])),
      [staff],
    ),
  );
  const toPerson = (mail.data ?? []).filter(
    (m) => m.disposition === "to_person",
  ).length;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Việc của tôi")}
        title="Việc của tôi"
        subtitle="Việc DW2 đang chờ bạn, quyết định trước."
        actions={
          hasScope(SCOPE.create) ? (
            <Link href="/purchasing/new">
              <Button type="primary" icon={<PlusOutlined aria-hidden />}>
                Tôi cần mua…
              </Button>
            </Link>
          ) : undefined
        }
      />
      {decides ? (
        <Card
          size="small"
          title={`Chờ bạn duyệt (${approvals.data?.length ?? "…"})`}
        >
          {approvals.error ? (
            <LoadError error={approvals.error} onRetry={approvals.reload} />
          ) : !approvals.data ? (
            <Skeleton active />
          ) : approvals.data.length === 0 ? (
            <Empty description="Không có gì chờ bạn duyệt." />
          ) : (
            <Flex vertical gap={16}>
              {approvals.data.map((a) =>
                CASE_APPROVALS.has(a.approval_type) ? (
                  <CaseApproval
                    key={a.id}
                    approval={a}
                    onDecided={() => {
                      approvals.reload();
                      cases.reload();
                    }}
                  />
                ) : (
                  <RuleApproval key={a.id} approval={a} />
                ),
              )}
            </Flex>
          )}
        </Card>
      ) : null}
      {staff ? (
        <Card size="small" title="Hồ sơ cần người làm">
          {cases.error ? (
            <LoadError error={cases.error} onRetry={cases.reload} />
          ) : (
            <CaseWork cases={cases.data?.items ?? null} toPerson={toPerson} />
          )}
        </Card>
      ) : null}
      {!staff && hasScope(SCOPE.readOwn) ? (
        <Card size="small" title="Yêu cầu của tôi">
          {cases.error ? (
            <LoadError error={cases.error} onRetry={cases.reload} />
          ) : (
            <Rows<PurchaseCase>
              loading={!cases.data}
              items={cases.data?.items ?? []}
              empty="Bạn chưa gửi yêu cầu nào."
              rowKey={(c) => c.case_id}
              render={(c) => (
                <Flex gap={8} wrap align="center">
                  <Link href={`/purchasing/requests/${c.case_id}`}>
                    {c.request.pr_no}
                  </Link>
                  <CaseStatusTag status={c.status} />
                  <Typography.Text>
                    {formatDateTime(c.received_at)}
                  </Typography.Text>
                </Flex>
              )}
            />
          )}
        </Card>
      ) : null}
    </div>
  );
}

// ----------------------------------------------------------- approvals --

function CaseApproval({
  approval,
  onDecided,
}: {
  approval: Approval;
  onDecided: () => void;
}) {
  const caseId = String(approval.payload.case_id ?? "");
  // Whoever is asked reads the case: a reader of every case, or an approver
  // through the scope this approval stamped (the server decides which).
  const found = useCachedResource<PurchaseCase | null>(
    `purchasing/case/${caseId}`,
    useCallback(
      () => (caseId ? purchasingApi().case(caseId) : Promise.resolve(null)),
      [caseId],
    ),
  );
  const c = found.data;
  const reapproval = approval.approval_type === "purchasing.reapproval";
  const version = c?.case_version ?? Number(approval.payload.case_version);
  const amount = reapproval
    ? c?.reapproval &&
      money(c.reapproval.selection.total, c.reapproval.selection.currency)
    : c?.check?.amount
      ? money(c.check.amount, c.check.currency)
      : c?.check
        ? "Chưa rõ: có dòng chưa có giá"
        : null;
  const findings = c?.check?.findings ?? [];
  const what = c ? `yêu cầu ${c.request.pr_no}` : "yêu cầu mua hàng";

  return (
    <Card
      size="small"
      type="inner"
      title={
        <Flex gap={8} wrap align="center">
          <span>
            {reapproval
              ? "Duyệt lại lựa chọn nhà cung cấp"
              : "Duyệt yêu cầu mua hàng"}
          </span>
          {c ? (
            <Link href={`/purchasing/requests/${c.case_id}`}>
              {c.request.pr_no}
            </Link>
          ) : null}
        </Flex>
      }
    >
      <Flex vertical gap={8}>
        {found.error ? <LoadError error={found.error} compact /> : null}
        {c ? (
          <>
            <Typography.Text>
              {c.request.department} · {c.request.requester} ·{" "}
              {c.request.lines.length} dòng
              {amount ? ` · ${amount}` : ""}
            </Typography.Text>
            <Typography.Text>
              Bậc duyệt:{" "}
              {(reapproval
                ? c.reapproval?.approval.tier_label
                : c.approval?.tier_label) ?? "không rõ"}{" "}
              · gửi {formatDateTime(approval.created_at)}
            </Typography.Text>
            {reapproval && c.reapproval?.explanation ? (
              <Flex vertical gap={4}>
                <MarkTag
                  mark="machine_written"
                  tip="DW2 viết lý do này; mọi con số trong đó là số của hệ thống."
                />
                <Typography.Paragraph className="mb-0">
                  {c.reapproval.explanation}
                </Typography.Paragraph>
              </Flex>
            ) : null}
            {!reapproval && findings.length ? (
              <Typography.Text>
                Cần biết:{" "}
                {findings
                  .map(
                    (f) =>
                      `${f.line_no ? `dòng ${f.line_no} ` : ""}${FINDING[f.code]}`,
                  )
                  .join("; ")}
              </Typography.Text>
            ) : null}
          </>
        ) : found.error ? (
          <Typography.Text>{approval.reason}</Typography.Text>
        ) : (
          <Skeleton active paragraph={{ rows: 1 }} />
        )}
        <DecideApproval
          approval={approval}
          subjectVersion={version}
          what={what}
          onDecided={onDecided}
        />
      </Flex>
    </Card>
  );
}

function RuleApproval({ approval }: { approval: Approval }) {
  const version = String(approval.payload.version ?? "");
  return (
    <Card size="small" type="inner" title="Duyệt phiên bản quy tắc">
      <Flex vertical gap={8}>
        <Typography.Text>
          Phiên bản {version} · gửi {formatDateTime(approval.created_at)}
        </Typography.Text>
        <Link
          href={`/purchasing/settings?version=${encodeURIComponent(String(approval.payload.version_id ?? ""))}`}
        >
          Xem thay đổi bằng lời và duyệt
        </Link>
      </Flex>
    </Card>
  );
}

// --------------------------------------------------------------- cases --

interface Work {
  c: PurchaseCase;
  todo: string;
}

/** What a person does next on a case, by its state and the viewer's scopes. */
function workOf(
  c: PurchaseCase,
  has: (scope: string) => boolean,
): string | null {
  if (c.status === "received" && c.review && !c.review.reviewed_at)
    return has(SCOPE.intake) ? "Xem lại yêu cầu máy đọc" : null;
  if (c.status === "approved")
    return has(SCOPE.rfq) ? "Soạn thư hỏi giá" : null;
  if (c.status === "rfq_drafted")
    return has(SCOPE.rfq) ? "Ghi báo giá và chọn nhà cung cấp" : null;
  if (c.status === "supplier_selected") return has(SCOPE.po) ? "Soạn PO" : null;
  if (c.status === "po_drafted")
    return has(SCOPE.po) ? "Tải file Bravo và nhập vào Bravo" : null;
  return null;
}

function CaseWork({
  cases,
  toPerson,
}: {
  cases: PurchaseCase[] | null;
  toPerson: number;
}) {
  const { hasScope } = useAuth();
  const work = useMemo<Work[]>(
    () =>
      (cases ?? []).flatMap((c) => {
        const todo = workOf(c, hasScope);
        return todo ? [{ c, todo }] : [];
      }),
    [cases, hasScope],
  );
  return (
    <Flex vertical gap={8}>
      {toPerson ? (
        <Link href="/purchasing/inbox">
          {toPerson} thư trong hộp thư mua hàng cần người xem
        </Link>
      ) : null}
      <Rows<Work>
        loading={cases === null}
        items={work}
        empty="Không có hồ sơ nào đang chờ bạn trong 50 hồ sơ mới nhất."
        rowKey={({ c }) => c.case_id}
        render={({ c, todo }) => (
          <Flex gap={8} wrap align="center">
            <Link href={`/purchasing/requests/${c.case_id}`}>
              {c.request.pr_no}
            </Link>
            <CaseStatusTag status={c.status} />
            <Typography.Text>{todo}</Typography.Text>
          </Flex>
        )}
      />
    </Flex>
  );
}
