"use client";

import { useCallback, useState, type ReactNode } from "react";
import {
  Button,
  Drawer,
  Empty,
  Skeleton,
  Space,
  Timeline,
  Typography,
} from "antd";
import {
  HistoryOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { StatusTag, type StatusTone } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import {
  formatDate,
  formatDateTime,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import {
  BRAVO_WRITE_STATUS,
  DECLINE_REASON,
  DESIGN_VERDICT,
  FINDING_CODE,
  FINDING_DISPOSITION,
  label,
  MAPPING_STATUS,
  TRAIL_ACTOR,
  TRAIL_KIND,
} from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";

type Trail = SalesSchemas["LineTrailView"];
type Step = SalesSchemas["TrailStepView"];
/** Which case's line: an order's PO line or a quotation's requested line. */
type CaseKind = "order" | "quote";

/** Who decided, in words and an icon, never colour alone (ui-quality §7). */
const ACTOR_LOOK: Record<Step["decided_by"], [StatusTone, ReactNode]> = {
  rule: ["outline", <SafetyCertificateOutlined key="i" aria-hidden />],
  model: ["geek", <RobotOutlined key="i" aria-hidden />],
  dw: ["pri", <ThunderboltOutlined key="i" aria-hidden />],
  person: ["ok", <UserOutlined key="i" aria-hidden />],
};

/**
 * "Vì sao dòng này đi như vậy" (ticket 62): a button on the line's detail
 * that opens the steps the line took, read only when opened. Short by
 * default (Đạt's rule): the drawer is the detail. The order and quote pages
 * both use it.
 */
export function LineTrailButton({
  kind,
  caseId,
  lineNo,
  version,
}: {
  kind: CaseKind;
  caseId: string;
  lineNo: number;
  /** Read again when the case moves: the page passes its version. */
  version: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        size="small"
        icon={<HistoryOutlined aria-hidden />}
        onClick={() => setOpen(true)}
      >
        Vì sao dòng {lineNo} đi như vậy
      </Button>
      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={`Dòng ${lineNo}: các bước đã đi`}
        size="min(560px, 100vw)"
        destroyOnHidden
      >
        {open ? (
          <LineTrail
            kind={kind}
            caseId={caseId}
            lineNo={lineNo}
            version={version}
          />
        ) : null}
      </Drawer>
    </>
  );
}

export function LineTrail({
  kind,
  caseId,
  lineNo,
  version,
}: {
  kind: CaseKind;
  caseId: string;
  lineNo: number;
  version: number;
}) {
  const name = usePeople();
  const trail = useResource<Trail>(
    `sales/${kind}/${caseId}/line/${lineNo}/trail@${version}`,
    useCallback(
      () => salesApi().lineTrail(kind, caseId, lineNo),
      [kind, caseId, lineNo],
    ),
  );
  if (trail.loading && !trail.data)
    return <Skeleton active paragraph={{ rows: 4 }} />;
  if (trail.error && !trail.data)
    return <LoadError compact error={trail.error} onRetry={trail.reload} />;
  const steps = trail.data?.steps ?? [];
  if (steps.length === 0)
    return <Empty description="Dòng này chưa có bước nào được ghi." />;
  const count = (who: Step["decided_by"]) =>
    steps.filter((s) => s.decided_by === who).length;
  return (
    <div className="space-y-3">
      <Typography.Paragraph className="!mb-0" role="status">
        {steps.length} bước: {count("rule")} do luật, {count("model")} do mô
        hình, {count("dw")} DW tự áp dụng, {count("person")} do người. Thời gian
        theo {TIME_ZONE_LABEL}.
      </Typography.Paragraph>
      <Timeline
        items={steps.map((step, index) => ({
          key: `${step.kind}:${step.code}:${index}`,
          content: <TrailStep step={step} name={name} />,
        }))}
      />
    </div>
  );
}

function title(step: Step): string {
  if (step.kind === "finding" || step.kind === "finding_decided")
    return `${label(TRAIL_KIND, step.kind)}: ${label(FINDING_CODE, step.code)}`;
  return label(TRAIL_KIND, step.kind);
}

/** Steps whose outcome is shown through its own label table above. */
const LABELLED_OUTCOME = new Set<Step["kind"]>([
  "mapping",
  "finding_decided",
  "bravo_write",
  "design_check",
  "declined",
]);

function facts(step: Step): string[] {
  const out: string[] = [];
  if (step.cell) out.push(`Ô ${step.cell}`);
  if (step.page) out.push(`Trang ${step.page}`);
  if (step.kind === "mapping" && step.outcome)
    out.push(label(MAPPING_STATUS, step.outcome));
  if (step.kind === "finding_decided" && step.outcome)
    out.push(label(FINDING_DISPOSITION, step.outcome));
  if (step.kind === "bravo_write" && step.outcome)
    out.push(label(BRAVO_WRITE_STATUS, step.outcome));
  if (step.kind === "design_check" && step.outcome)
    out.push(label(DESIGN_VERDICT, step.outcome));
  if (step.kind === "declined" && step.outcome)
    out.push(label(DECLINE_REASON, step.outcome));
  if (step.value) out.push(step.value);
  if (step.valid_from || step.valid_to)
    out.push(
      `hiệu lực ${formatDate(step.valid_from)} – ${step.valid_to ? formatDate(step.valid_to) : "không hết hạn"}`,
    );
  if (step.rule_version) out.push(`quy tắc ${step.rule_version}`);
  if (!LABELLED_OUTCOME.has(step.kind) && step.outcome) out.push(step.outcome);
  if (step.confidence != null)
    out.push(`độ chắc ${Math.round(step.confidence * 100)}%`);
  if (step.examples) out.push(`đã xem ${step.examples} dòng đã quyết`);
  return out;
}

function TrailStep({
  step,
  name,
}: {
  step: Step;
  name: (id: string | null | undefined) => string;
}) {
  const [tone, icon] = ACTOR_LOOK[step.decided_by];
  const who = step.decided_by === "person" ? name(step.actor_user_id) : null;
  const shown = facts(step);
  return (
    <div className="space-y-1">
      <Space wrap size={[8, 4]}>
        <StatusTag tone={tone} icon={icon}>
          {label(TRAIL_ACTOR, step.decided_by)}
        </StatusTag>
        <Typography.Text strong>{title(step)}</Typography.Text>
        <Typography.Text code>{step.code}</Typography.Text>
      </Space>
      {who || step.at ? (
        <div>
          <Typography.Text>
            {[who, step.at ? formatDateTime(step.at) : null]
              .filter(Boolean)
              .join(" · ")}
          </Typography.Text>
        </div>
      ) : null}
      {shown.length ? (
        <div>
          <Typography.Text>{shown.join(" · ")}</Typography.Text>
        </div>
      ) : null}
    </div>
  );
}
