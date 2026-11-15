import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime, formatDuration, instantMs } from "../../../lib/dates";

type WorkItem = SalesSchemas["WorkItem"];

/**
 * Where an item stands against its SLA (tickets 47, 48). The times are the
 * server's (`WorkItem.sla_warn_at`, `sla_due_at`, from the tenant's
 * follow-up timings: the reminder and the escalation to the head); the
 * screen holds no threshold of its own.
 */
export type SlaState = "late" | "soon" | "on_time" | "none";

export interface SlaReading {
  state: SlaState;
  /** When the item is late, in milliseconds; null without an SLA. */
  dueMs: number | null;
  /** "còn 3 giờ 10 phút" / "quá hạn 2 giờ"; empty without an SLA. */
  relative: string;
  /** "09:12 06/10/2026"; the zone is in the column header. */
  absolute: string;
}

export function slaOf(item: WorkItem, now: number): SlaReading {
  const dueMs = instantMs(item.sla_due_at);
  const warnMs = instantMs(item.sla_warn_at);
  if (dueMs === null)
    return { state: "none", dueMs: null, relative: "", absolute: "" };
  const left = dueMs - now;
  const state: SlaState =
    left <= 0 ? "late" : warnMs !== null && now >= warnMs ? "soon" : "on_time";
  return {
    state,
    dueMs,
    relative:
      left <= 0
        ? `quá hạn ${formatDuration(-left)}`
        : `còn ${formatDuration(left)}`,
    absolute: formatDateTime(item.sla_due_at, { zoneLabel: false }),
  };
}

const RANK: Record<SlaState, number> = {
  late: 0,
  soon: 1,
  on_time: 2,
  none: 3,
};

/**
 * The work list in the order a person should take it: late first, then about
 * to be, then by when each is late; an item no SLA times keeps the server's
 * order (due date, then the oldest) after them. The whole list is loaded
 * (`SalesApi.myWork` reads every page), so this order is the list's, not a
 * page's.
 */
export function bySla(items: readonly WorkItem[], now: number): WorkItem[] {
  const read = new Map(items.map((item) => [item, slaOf(item, now)]));
  return items
    .map((item, index) => ({ item, index, sla: read.get(item)! }))
    .sort(
      (a, b) =>
        RANK[a.sla.state] - RANK[b.sla.state] ||
        (a.sla.dueMs ?? 0) - (b.sla.dueMs ?? 0) ||
        a.index - b.index,
    )
    .map(({ item }) => item);
}

/** "order:<id>" from the deep link `/sales?item=order:<id>` (ticket 48). */
export function itemKey(item: Pick<WorkItem, "kind" | "id">): string {
  return `${item.kind}:${item.id}`;
}
