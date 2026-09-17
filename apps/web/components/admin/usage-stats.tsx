"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, Wrench } from "lucide-react";
import type { UsageOverview } from "@dw/contracts";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  cn,
} from "@dw/ui";
import { apiClient } from "../../lib/session";

/**
 * F6 — which AI usecases are used, how often, and what they cost.
 *
 * Everything on this panel is read from `platform.model_usage_ledger` (one
 * row per model call, one `run_id` per click/turn), so the table answers
 * with measured numbers, not estimates. Numbers exist from the day metering
 * shipped (2026-08-26) — the footer says so rather than letting an empty
 * early month read as "nobody used anything".
 *
 * Form choices follow the dataviz method: many usecases × several measures
 * is a TABLE; the day-by-day frequency is a single-series bar chart (one
 * hue, no legend needed); the headline totals are stat tiles. Text wears
 * ink tokens; the one series hue carries no identity beyond "usage".
 */

const RANGES = [7, 30, 90] as const;

// PLUG-IN POINT: the usecase keys the meters stamp, in the team's own words.
// A bounded context adds its worker ids here. An unknown key still renders (as
// its raw id) — a new meter must not vanish from this table.
const USECASE_VI: Record<string, string> = {
  "(unattributed)": "Chưa gắn usecase",
};

function labelOf(workerId: string): string {
  return USECASE_VI[workerId] ?? workerId;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function formatDay(iso: string): string {
  const parsed = new Date(iso);
  return parsed.toLocaleDateString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
  });
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Every day of the window, zero-filled — a quiet day must show as a gap of
    nothing, not vanish and squeeze the timeline. */
function dailyTotals(
  overview: UsageOverview,
): { day: string; runs: number; cost: number }[] {
  const byDay = new Map<string, { runs: number; cost: number }>();
  for (const row of overview.daily) {
    const key = row.day.slice(0, 10);
    const current = byDay.get(key) ?? { runs: 0, cost: 0 };
    byDay.set(key, {
      runs: current.runs + row.runs,
      cost: current.cost + row.cost_usd,
    });
  }
  const days: { day: string; runs: number; cost: number }[] = [];
  const cursor = new Date(overview.since);
  const today = new Date();
  while (cursor <= today) {
    const key = cursor.toISOString().slice(0, 10);
    const entry = byDay.get(key) ?? { runs: 0, cost: 0 };
    days.push({ day: key, runs: entry.runs, cost: entry.cost });
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

export function UsageStatsPanel() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const [overview, setOverview] = useState<UsageOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setOverview(await apiClient().getUsageStats(days));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const totals = useMemo(() => {
    if (!overview) return null;
    const runs = overview.usecases.reduce((sum, u) => sum + u.runs, 0);
    const calls = overview.usecases.reduce((sum, u) => sum + u.model_calls, 0);
    const cost = overview.usecases.reduce(
      (sum, u) => sum + (u.cost_usd ?? 0),
      0,
    );
    const unpriced = overview.usecases.reduce(
      (sum, u) => sum + u.unpriced_calls,
      0,
    );
    const top = overview.usecases.find((u) => u.cost_usd !== null);
    return { runs, calls, cost, unpriced, top };
  }, [overview]);

  const series = useMemo(
    () => (overview ? dailyTotals(overview) : []),
    [overview],
  );
  const maxRuns = Math.max(1, ...series.map((d) => d.runs));

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>Sổ usage của tenant</CardTitle>
          <CardDescription>
            Mỗi lượt bấm / lượt chạy AI là một run trong sổ; chi phí tính theo
            bảng giá route trong configs/models.
          </CardDescription>
        </div>
        <div className="flex items-center gap-1.5">
          {/* The one filter row, above every chart (interaction spec). */}
          <div
            className="inline-flex rounded-md border bg-card p-0.5"
            role="tablist"
          >
            {RANGES.map((range) => (
              <button
                key={range}
                type="button"
                role="tab"
                aria-selected={days === range}
                onClick={() => setDays(range)}
                className={cn(
                  "rounded px-2 py-1 text-[11px] font-medium",
                  days === range
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {range} ngày
              </button>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {loading && !overview && <Skeleton className="h-40 w-full" />}
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm">
            Không đọc được sổ usage: {error}
          </div>
        )}

        {overview && totals && (
          <>
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="rounded-xl border bg-card px-3.5 py-3">
                <p className="text-xs text-muted-foreground">
                  Lượt chạy AI ({overview.days} ngày)
                </p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {totals.runs.toLocaleString("vi-VN")}
                </p>
                <p className="text-xs text-muted-foreground">
                  {totals.calls.toLocaleString("vi-VN")} call model
                </p>
              </div>
              <div className="rounded-xl border bg-card px-3.5 py-3">
                <p className="text-xs text-muted-foreground">Chi phí model</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">
                  {formatUsd(totals.cost)}
                </p>
                {totals.unpriced > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {totals.unpriced.toLocaleString("vi-VN")} call chưa định giá
                  </p>
                )}
              </div>
              <div className="rounded-xl border bg-card px-3.5 py-3">
                <p className="text-xs text-muted-foreground">Tốn nhất</p>
                <p className="mt-1 truncate text-xl font-semibold">
                  {totals.top ? labelOf(totals.top.worker_id) : "—"}
                </p>
                {totals.top?.cost_usd != null && (
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {formatUsd(totals.top.cost_usd)}
                  </p>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Tần suất theo ngày
              </h3>
              {/* One series, one hue; 4px rounded data-ends anchored to the
                  baseline, 2px gaps, hover answers the exact numbers. */}
              <div
                className="mt-2 flex h-28 items-end gap-0.5 rounded-xl border bg-card px-3 pb-2 pt-3"
                role="img"
                aria-label={`Số lượt chạy AI theo ngày trong ${overview.days} ngày`}
              >
                {series.map((point) => (
                  <div
                    key={point.day}
                    title={`${formatDay(point.day)} · ${point.runs} lượt · ${formatUsd(point.cost)}`}
                    className="group flex h-full flex-1 flex-col justify-end"
                  >
                    <div
                      className={cn(
                        "w-full rounded-t",
                        point.runs > 0
                          ? "bg-sky-600 group-hover:bg-sky-700"
                          : "bg-muted",
                      )}
                      style={{
                        height:
                          point.runs > 0
                            ? `${Math.max(6, (point.runs / maxRuns) * 100)}%`
                            : 2,
                      }}
                    />
                  </div>
                ))}
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>{formatDay(series[0]?.day ?? "")}</span>
                <span>tối đa {maxRuns.toLocaleString("vi-VN")} lượt/ngày</span>
                <span>{formatDay(series[series.length - 1]?.day ?? "")}</span>
              </div>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Theo usecase
              </h3>
              <div className="mt-2 overflow-x-auto rounded-xl border bg-card">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Tính năng</th>
                      <th className="px-3 py-2.5 text-right font-medium">
                        Lượt
                      </th>
                      <th className="px-3 py-2.5 text-right font-medium">
                        Call
                      </th>
                      <th className="px-3 py-2.5 text-right font-medium">
                        Tokens vào/ra
                      </th>
                      <th className="px-3 py-2.5 text-right font-medium">
                        Chi phí
                      </th>
                      <th className="px-4 py-2.5 text-right font-medium">
                        Lần cuối
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.usecases.length === 0 && (
                      <tr>
                        <td
                          colSpan={6}
                          className="px-4 py-6 text-center text-muted-foreground"
                        >
                          Chưa có lượt dùng nào trong khoảng này.
                        </td>
                      </tr>
                    )}
                    {overview.usecases.map((usecase) => (
                      <tr
                        key={usecase.worker_id}
                        className="border-b last:border-0"
                      >
                        <td className="px-4 py-2">
                          <p className="font-medium">
                            {labelOf(usecase.worker_id)}
                          </p>
                          <p className="font-mono text-[10.5px] text-muted-foreground">
                            {usecase.worker_id}
                          </p>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {usecase.runs.toLocaleString("vi-VN")}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {usecase.model_calls.toLocaleString("vi-VN")}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatTokens(usecase.input_tokens)} /{" "}
                          {formatTokens(usecase.output_tokens)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {usecase.cost_usd === null ? (
                            <span className="text-xs italic text-muted-foreground">
                              chưa định giá
                            </span>
                          ) : (
                            <>
                              {formatUsd(usecase.cost_usd)}
                              {usecase.unpriced_calls > 0 && (
                                <span className="ml-1 text-[10px] text-muted-foreground">
                                  (+{usecase.unpriced_calls} chưa giá)
                                </span>
                              )}
                            </>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right text-xs text-muted-foreground tabular-nums">
                          {formatWhen(usecase.last_used_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {overview.tools.length > 0 && (
              <div>
                <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Wrench className="size-3.5" />
                  Tool agent đã gọi
                </h3>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {overview.tools.map((tool) => (
                    <div
                      key={tool.tool_name}
                      className="rounded-xl border bg-card px-3.5 py-2.5"
                    >
                      <p className="font-mono text-xs text-muted-foreground">
                        {tool.tool_name}
                      </p>
                      <p className="mt-0.5 text-lg font-semibold tabular-nums">
                        {tool.calls.toLocaleString("vi-VN")}
                        {tool.failed > 0 && (
                          <span className="ml-2 text-xs font-normal text-muted-foreground">
                            {tool.failed} lỗi
                          </span>
                        )}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="text-[11px] leading-snug text-muted-foreground">
              Số liệu có từ ngày bật đo (26/08/2026) — các lượt chạy trước đó
              không được ghi sổ nên không hiện ở đây. Số cũ của các lane thầu
              (trước khi tách tên) nằm dưới &quot;Nghiên cứu công ty&quot;.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
