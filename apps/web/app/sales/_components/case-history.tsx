"use client";

import { useCallback } from "react";
import { Card, Skeleton, Steps, theme, Timeline, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import {
  CASE_EVENT,
  CLOSE_REASON,
  DECLINE_REASON,
  label,
  ORDER_STATE,
  QUOTE_STATE,
} from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";

type Entry = SalesSchemas["CaseHistoryEntry"];

/**
 * The case's own pipeline: the statuses it actually passed through, in the
 * order it passed them (read from its events, so a step it skipped is not
 * drawn as done), the one it is in now, and under it every event, oldest
 * first, with who did it. The WIV steps beside it (`CaseTimeline`) say where
 * the case sits in the surveyed procedure; this says how it got there.
 */
export function CaseHistory({
  kind,
  caseId,
  status,
  version,
}: {
  kind: "order" | "quote";
  caseId: string;
  status: string;
  /** Read again when the case moves: the page passes its version. */
  version: number;
}) {
  const { token } = theme.useToken();
  const person = usePeople();
  const history = useResource<Entry[]>(
    `sales/${kind}/${caseId}/history@${version}`,
    useCallback(() => salesApi().history(kind, caseId), [kind, caseId]),
  );
  const states = kind === "order" ? ORDER_STATE : QUOTE_STATE;
  const reasons = kind === "order" ? CLOSE_REASON : DECLINE_REASON;

  if (history.loading && !history.data)
    return (
      <Card size="small" title="Hành trình hồ sơ">
        <Skeleton active paragraph={{ rows: 3 }} />
      </Card>
    );
  if (history.error && !history.data)
    return (
      <Card size="small" title="Hành trình hồ sơ">
        <LoadError compact error={history.error} onRetry={history.reload} />
      </Card>
    );
  const entries = history.data ?? [];
  // The statuses in the order the case entered them, each once, the current
  // one last even when it was entered before (a case sent back).
  const path: string[] = [];
  for (const e of entries)
    if (e.to_status !== e.from_status && path.at(-1) !== e.to_status)
      path.push(e.to_status);
  if (path.at(-1) !== status) path.push(status);
  const terminal = status === "closed" || status === "declined";

  return (
    <Card
      size="small"
      title="Hành trình hồ sơ"
      extra={
        <Typography.Text
          type="secondary"
          style={{ fontSize: token.fontSizeSM }}
        >
          {TIME_ZONE_LABEL}
        </Typography.Text>
      }
    >
      <div className="space-y-3">
        <div className="overflow-x-auto pb-1">
          <Steps
            size="small"
            aria-label="Các trạng thái hồ sơ đã qua"
            current={path.length - 1}
            status={terminal ? "error" : "process"}
            items={path.map((s) => ({ title: label(states, s) }))}
          />
        </div>
        {entries.length === 0 ? (
          <Typography.Text type="secondary">
            Chưa có sự kiện nào được ghi cho hồ sơ này.
          </Typography.Text>
        ) : (
          <Timeline
            items={[...entries].reverse().map((e, i) => ({
              key: `${e.occurred_at}-${i}`,
              color: e.actor_kind === "worker" ? "gray" : "blue",
              content: (
                <div>
                  <Typography.Text strong>
                    {label(CASE_EVENT, e.action)}
                  </Typography.Text>
                  {e.to_status !== e.from_status && (
                    <Typography.Text type="secondary">
                      {" "}
                      → {label(states, e.to_status)}
                    </Typography.Text>
                  )}
                  {e.reason_code && (
                    <Typography.Text type="secondary">
                      {" "}
                      ({label(reasons, e.reason_code)})
                    </Typography.Text>
                  )}
                  <div>
                    <Typography.Text
                      type="secondary"
                      style={{ fontSize: token.fontSizeSM }}
                    >
                      {formatDateTime(e.occurred_at, { zoneLabel: false })} ·{" "}
                      {e.actor_kind === "worker"
                        ? "DW1"
                        : e.actor_user_id
                          ? person(e.actor_user_id)
                          : "Không rõ người làm"}
                    </Typography.Text>
                  </div>
                </div>
              ),
            }))}
          />
        )}
      </div>
    </Card>
  );
}
