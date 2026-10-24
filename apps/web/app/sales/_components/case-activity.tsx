"use client";

import { useCallback } from "react";
import { FileSearchOutlined } from "@ant-design/icons";
import { Button, Card, Skeleton, Tag, theme, Timeline, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import {
  formatDateTime,
  formatLatency,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import {
  entryReason,
  entryResult,
  modelStepLabel,
  producedField,
  producedValue,
  reasonLabel,
} from "../_lib/activity";
import { ACTIVITY_KIND, FIELD, label } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { ActivityResultTag } from "./tags";

type View = SalesSchemas["CaseActivityView"];
type Entry = SalesSchemas["ActivityEntry"];
type Anchor = SalesSchemas["AnchorRef"];

const TITLE = "DW1 đã làm gì";

/**
 * "DW1 đã làm gì" (slice 3): each thing a model step did on the case, oldest
 * first, from `GET /sales/{orders|quotes}/{id}/activity`. Per entry: the step,
 * the result in words (accepted, handed to a person, no answer from the
 * model) and why, the values it read with a way to their source, who took it
 * over, and the model, prompt and time in secondary text.
 *
 * What the entries carry is the server's: a price is absent from them for
 * someone who may not read prices, so nothing here hides one, and nothing
 * here can show one that was not sent.
 */
export function CaseActivity({
  kind,
  caseId,
  version,
  onOpenSource,
}: {
  kind: "order" | "quote";
  caseId: string;
  /** Read again when the case moves: the page passes its version. */
  version: number;
  /** Opens the case's source drawer at a value's anchor. */
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  const { token } = theme.useToken();
  const activity = useResource<View>(
    `sales/${kind}/${caseId}/activity@${version}`,
    useCallback(() => salesApi().caseActivity(kind, caseId), [kind, caseId]),
  );

  if (activity.loading && !activity.data)
    return (
      <Card size="small" title={TITLE}>
        <Skeleton active paragraph={{ rows: 3 }} />
      </Card>
    );
  if (activity.error && !activity.data)
    return (
      <Card size="small" title={TITLE}>
        <LoadError compact error={activity.error} onRetry={activity.reload} />
      </Card>
    );
  const entries = activity.data?.entries ?? [];
  // A step's calls and time are for the whole mail: the server repeats them
  // on each of its entries (one per line), so they are said once, on the
  // first entry of each (message, step), with how many entries they cover.
  const groupSize = new Map<string, number>();
  for (const e of entries)
    groupSize.set(timingKey(e), (groupSize.get(timingKey(e)) ?? 0) + 1);
  const timed = new Set<string>();
  const timingOf = (entry: Entry): Timing | null => {
    const key = timingKey(entry);
    if (timed.has(key) || !entry.calls) return null;
    timed.add(key);
    return {
      calls: entry.calls,
      durationMs: entry.duration_ms,
      entries: groupSize.get(key) ?? 1,
    };
  };
  return (
    <Card
      size="small"
      title={TITLE}
      extra={
        <Typography.Text
          type="secondary"
          style={{ fontSize: token.fontSizeSM }}
        >
          {TIME_ZONE_LABEL}
        </Typography.Text>
      }
    >
      {entries.length === 0 ? (
        <Typography.Text>DW1 chưa làm gì ở hồ sơ này.</Typography.Text>
      ) : (
        <Timeline
          items={entries.map((entry, i) => ({
            key: `${entry.occurred_at}-${entry.step}-${entry.line_no ?? 0}-${i}`,
            content: (
              <EntryView
                entry={entry}
                timing={timingOf(entry)}
                onOpenSource={onOpenSource}
              />
            ),
          }))}
        />
      )}
    </Card>
  );
}

/** The model calls of one step on one mail, said on its first entry. */
interface Timing {
  calls: number;
  durationMs: number | null;
  /** How many entries of this mail and step the calls covered. */
  entries: number;
}

function timingKey(entry: Entry): string {
  return `${entry.message_id}|${entry.step}`;
}

/** "3 lần gọi, 4,2 giây", and for whom when it covered several entries. */
export function timingWords(timing: Timing): string {
  const head = `${timing.calls} lần gọi, ${formatLatency(timing.durationMs)}`;
  return timing.entries > 1
    ? `${head} cho cả thư (${timing.entries} mục của bước này)`
    : head;
}

function anchorName(anchor: Anchor): string {
  const field = label(FIELD, anchor.field) || anchor.field;
  return anchor.line_no ? `Dòng ${anchor.line_no} · ${field}` : field;
}

function EntryView({
  entry,
  timing,
  onOpenSource,
}: {
  entry: Entry;
  timing: Timing | null;
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  const { token } = theme.useToken();
  const person = usePeople();
  const result = entryResult(entry);
  const reason = entryReason(entry);
  // One way to the source per place the values were read from.
  const anchors = new Map<string, Anchor>();
  for (const p of entry.produced)
    if (p.anchor)
      anchors.set(`${p.anchor.line_no}:${p.anchor.field}`, p.anchor);
  const refusals = Object.entries(entry.refusals);
  return (
    <div className="flex flex-col items-start gap-1" data-activity={entry.step}>
      <span className="flex flex-wrap items-center gap-2">
        <Typography.Text strong>{modelStepLabel(entry.step)}</Typography.Text>
        {entry.process_steps.map((s) => (
          <Tag key={s} className="me-0">
            {s}
          </Tag>
        ))}
        <ActivityResultTag result={result} />
      </span>
      <span>
        {ACTIVITY_KIND[entry.kind]}
        {entry.line_no ? ` · dòng ${entry.line_no}` : ""}
      </span>
      {reason ? <span>Lý do: {reason}</span> : null}
      {refusals.length ? (
        <span>
          DW1 bỏ qua:{" "}
          {refusals
            .map(([code, count]) => `${reasonLabel(code)} (${count})`)
            .join("; ")}
        </span>
      ) : null}
      {entry.produced.length ? (
        <div className="flex flex-col gap-1">
          <span>Giá trị đọc được:</span>
          <ul className="m-0 flex list-none flex-col gap-0 p-0">
            {entry.produced.map((p, i) => (
              <li key={`${p.field}-${p.line_no ?? 0}-${i}`}>
                {p.line_no ? `Dòng ${p.line_no} · ` : ""}
                {producedField(p.field)}:{" "}
                {producedValue(entry.step, p.field, p.value)}
              </li>
            ))}
          </ul>
          {anchors.size ? (
            <span className="flex flex-wrap gap-2">
              {[...anchors.values()].map((anchor) => (
                <Button
                  key={`${anchor.line_no}:${anchor.field}`}
                  size="small"
                  icon={<FileSearchOutlined aria-hidden />}
                  onClick={() => onOpenSource(anchor.field, anchor.line_no)}
                >
                  Xem nguồn: {anchorName(anchor)}
                </Button>
              ))}
            </span>
          ) : null}
        </div>
      ) : null}
      {entry.handled_by === "person" ? (
        <span>
          Người tiếp nhận:{" "}
          {entry.taken_over_by
            ? person(entry.taken_over_by)
            : "chưa ai tiếp nhận"}
        </span>
      ) : null}
      <Typography.Text type="secondary" style={{ fontSize: token.fontSizeSM }}>
        {formatDateTime(entry.occurred_at, { zoneLabel: false })} · mô hình{" "}
        {entry.model ?? "không rõ"} · {entry.prompt}
        {timing ? ` · ${timingWords(timing)}` : ""}
      </Typography.Text>
    </div>
  );
}
