"use client";

import { EnterOutlined } from "@ant-design/icons";
import { Alert, Card, Steps, theme, Typography } from "antd";
import { useSalesFrame } from "./sales-frame";
import {
  label,
  ORDER_STATE,
  PROCEDURE,
  QUOTE_STATE,
  STEP_COVERAGE,
} from "../_lib/labels";

/**
 * The case's place in its procedure (V3BidOverview's gate timeline, re-cut to
 * the WIV steps): the steps and the states each one holds come from the API's
 * overview (`WIV_STEPS`), so this draws no step table of its own. The current
 * steps are the ones whose states hold the case's state. No other step is drawn
 * as done: DW1 runs its checks before the Bravo entry (the spec's deviation),
 * so the WIV order is not the order a case passes through, and a step drawn
 * as passed because it sits to the left would be a claim nobody made. A step
 * outside this slice says so. Under the steps, who acts next.
 */
export function CaseTimeline({
  procedure,
  status,
  next,
}: {
  procedure: "WIV-03-012" | "WIV-03-023";
  status: string;
  /** Who acts next, in words (from my-work when it is the viewer). */
  next: string;
}) {
  const { overview } = useSalesFrame();
  const { token } = theme.useToken();
  const steps = (overview.data?.steps ?? []).filter(
    (s) => s.procedure === procedure,
  );
  const states = procedure === "WIV-03-012" ? ORDER_STATE : QUOTE_STATE;
  if (!steps.length)
    return (
      <Alert
        type="info"
        showIcon
        title={`Trạng thái: ${label(states, status)}`}
        description={next}
      />
    );
  return (
    <Card size="small" title={`Quy trình ${label(PROCEDURE, procedure)}`}>
      <div className="space-y-3">
        <div className="overflow-x-auto pb-1">
          <Steps
            size="small"
            aria-label="Các bước của quy trình"
            items={steps.map((step) => ({
              title: step.step_id,
              status: !step.states.includes(status)
                ? "wait"
                : status === "closed" || status === "declined"
                  ? "error"
                  : "process",
              content: step.states.includes(status)
                ? label(states, status)
                : step.coverage === "yes"
                  ? undefined
                  : label(STEP_COVERAGE, step.coverage),
            }))}
          />
        </div>
        <Typography.Text strong style={{ color: token.colorPrimaryText }}>
          <EnterOutlined aria-hidden className="me-1.5 -scale-x-100" />
          {next}
        </Typography.Text>
      </div>
    </Card>
  );
}
