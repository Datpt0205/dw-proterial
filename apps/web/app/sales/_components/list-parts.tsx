"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ClockCircleOutlined,
  CloseOutlined,
  RightOutlined,
  SearchOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Button,
  Card,
  Grid,
  Input,
  Segmented,
  Select,
  theme,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { CaseListActivity } from "@dw/api-client";
import { STATUS_TONES, type StatusTone } from "@dw/ui";
import { dayDeadline, UNKNOWN_TIME } from "../../../lib/dates";
import { initials } from "../../../lib/initials";
import { describeActivity } from "../_lib/activity";

/**
 * The pieces every Sales list is drawn with, from the prototype's list
 * screens: the "Cần xử lý" panel, the toolbar (tabs with counts, search,
 * sort), the two-line row title, the assignee and the deadline. One copy, so
 * the four lists read alike (ui-quality §1).
 */

const HOUR = 3_600_000;

// ------------------------------------------------------------ Cần xử lý --

export interface PriorityItem {
  key: string;
  /** What kind of urgency: the dot's colour; the lead says it in words. */
  tone: Extract<StatusTone, "err" | "warn" | "pri" | "unk" | "ok">;
  /** The words that carry the meaning ("Quá hạn", "3 thư chưa xử lý"). */
  lead: ReactNode;
  text?: ReactNode;
  sub?: ReactNode;
  /** Where the row goes: the record, or the list filtered to it. */
  href?: string;
  extra?: ReactNode;
}

/**
 * "Cần xử lý": what on this list needs someone first, one line each, each a
 * link to it. A list with nothing urgent says so instead of drawing nothing.
 */
export function PriorityPanel({
  items,
  calm,
}: {
  items: PriorityItem[];
  /** The sentence when nothing is urgent. */
  calm: string;
}) {
  const { token } = theme.useToken();
  const dot: Record<PriorityItem["tone"], string> = {
    err: token.colorError,
    warn: token.colorWarning,
    pri: token.colorPrimary,
    unk: STATUS_TONES.unk.fg,
    ok: token.colorSuccess,
  };
  const rows = items.length
    ? items
    : [{ key: "calm", tone: "ok" as const, lead: calm }];
  return (
    <Card
      size="small"
      title="Cần xử lý"
      styles={{ body: { padding: 0 } }}
      aria-label="Cần xử lý"
    >
      <ul className="m-0 list-none p-0">
        {rows.map((item, index) => {
          const body = (
            <span className="flex min-w-0 items-center gap-3 px-3 py-2.5">
              <span
                aria-hidden
                className="size-1.5 shrink-0 rounded-full"
                style={{ background: dot[item.tone] }}
              />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="min-w-0">
                  <Typography.Text strong>{item.lead}</Typography.Text>
                  {item.text ? (
                    <Typography.Text> {item.text}</Typography.Text>
                  ) : null}
                </span>
                {item.sub ? (
                  <Typography.Text type="secondary">{item.sub}</Typography.Text>
                ) : null}
              </span>
              {"extra" in item && item.extra ? item.extra : null}
              {"href" in item && item.href ? (
                <RightOutlined aria-hidden />
              ) : null}
            </span>
          );
          return (
            <li
              key={item.key}
              style={{
                borderTop: index
                  ? `1px solid ${token.colorBorderSecondary}`
                  : undefined,
              }}
            >
              {"href" in item && item.href ? (
                <Link
                  href={item.href}
                  className="block text-foreground hover:bg-muted"
                >
                  {body}
                </Link>
              ) : (
                body
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// -------------------------------------------------------------- toolbar --

export interface ListTab<T extends string> {
  value: T;
  label: string;
  count: number;
}

/**
 * Tabs with counts, a search the browser runs over the loaded rows, a filter
 * slot, and a sort. Every value is in the URL (`useListView`).
 */
export function ListToolbar<Tab extends string, Sort extends string>({
  tabs,
  tab,
  onTab,
  query,
  onQuery,
  placeholder,
  filter,
  sorts,
  sort,
  onSort,
}: {
  tabs: ListTab<Tab>[];
  tab: Tab;
  onTab: (tab: Tab) => void;
  query: string;
  onQuery: (query: string) => void;
  /** An example of what can be typed; the field's name is "Tìm". */
  placeholder: string;
  filter?: ReactNode;
  sorts: { value: Sort; label: string }[];
  sort: Sort;
  onSort: (sort: Sort) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="max-w-full overflow-x-auto">
        <Segmented<Tab>
          aria-label="Nhóm"
          value={tab}
          onChange={onTab}
          options={tabs.map((t) => ({
            value: t.value,
            label: (
              <span>
                {t.label}{" "}
                <Typography.Text type="secondary">{t.count}</Typography.Text>
              </span>
            ),
          }))}
        />
      </div>
      <Input
        allowClear
        aria-label="Tìm trong danh sách"
        prefix={<SearchOutlined aria-hidden />}
        placeholder={placeholder}
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        className="w-full sm:w-80"
      />
      {filter}
      <Select<Sort>
        aria-label="Sắp xếp"
        value={sort}
        onChange={onSort}
        options={sorts}
        className="w-full sm:ml-auto sm:w-56"
      />
    </div>
  );
}

// ------------------------------------------------------------ the rows --

/** Below antd's `md` (768 px), where a Sales list draws its phone layout:
 * measured, `xs` or `sm` matching. Until antd has measured (and wherever no
 * width matches at all) it is a desk: nothing is hidden on a guess. */
export function useIsPhone(): boolean {
  const screens = Grid.useBreakpoint();
  return screens.md === false && (screens.xs === true || screens.sm === true);
}

/**
 * A list's columns as a phone draws them: below `md` only the first column,
 * whose `RowTitle` carries a `phone` line with what the hidden columns say
 * that matters there, and any column `keep` names because it holds the row's
 * action. A column pinned right is pinned only from `md`, where there is room
 * for it. 2026-10-27, at 390 px: each list showed its first column and the
 * deadline, state and owner sat off-screen to the right.
 */
export function usePhoneColumns() {
  const isPhone = useIsPhone();
  return function phone<T>(
    columns: ColumnsType<T>,
    keep: readonly string[] = [],
  ): ColumnsType<T> {
    if (!isPhone) return columns;
    return columns
      .filter((column, i) => i === 0 || keep.includes(String(column.key)))
      .map((column) => ({ ...column, fixed: undefined }));
  };
}

/**
 * How a Sales list's table sits on a phone: laid out to the screen's width,
 * never scrolled sideways, so a long title ends in "…" instead of running off
 * the edge (2026-10-27). On a desk, as wide as its content.
 */
export function usePhoneTable() {
  const isPhone = useIsPhone();
  return {
    scroll: (y?: number) => ({ x: isPhone ? undefined : "max-content", y }),
    tableLayout: isPhone ? ("fixed" as const) : undefined,
  };
}

/**
 * The row's two lines: its name, which is the link (opens in a new tab,
 * truncated with the whole on hover), over its identifier in monospace and
 * whatever else identifies it. An identifier is never truncated. `phone` is
 * a third line drawn on a phone only (`usePhoneColumns`).
 */
export function RowTitle({
  href,
  title,
  code,
  sub,
  phone,
}: {
  href: string;
  title: string;
  code?: string | null;
  sub?: ReactNode;
  phone?: ReactNode;
}) {
  const { token } = theme.useToken();
  const isPhone = useIsPhone();
  return (
    <span className="flex min-w-0 max-w-md flex-col">
      <Link href={href} className="min-w-0 text-foreground hover:underline">
        <Typography.Text strong ellipsis={{ tooltip: title }}>
          {title}
        </Typography.Text>
      </Link>
      <span className="flex min-w-0 items-baseline gap-1">
        {code ? (
          <Typography.Text
            type="secondary"
            className="shrink-0 whitespace-nowrap"
            style={{ fontFamily: token.fontFamilyCode }}
          >
            {code}
          </Typography.Text>
        ) : null}
        {sub ? (
          <Typography.Text
            type="secondary"
            className="min-w-0"
            ellipsis={{ tooltip: sub }}
          >
            {code ? "· " : null}
            {sub}
          </Typography.Text>
        ) : null}
      </span>
      {phone && isPhone ? (
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          {phone}
        </span>
      ) : null}
    </span>
  );
}

/** Who holds the row: initials, the whole name on hover, focus and to a reader. */
export function Assignee({
  name,
  none = "Chưa giao",
  group = false,
}: {
  name: string | null;
  none?: string;
  /** A whole role holds it, not one person: a team mark, not initials. */
  group?: boolean;
}) {
  const { token } = theme.useToken();
  if (!name) return <Typography.Text type="secondary">{none}</Typography.Text>;
  return (
    <Tooltip title={name}>
      <span
        tabIndex={0}
        role="img"
        aria-label={`Phụ trách: ${name}`}
        className="inline-flex"
      >
        <Avatar
          size={28}
          aria-hidden
          style={{
            backgroundColor: token.colorFill,
            color: token.colorText,
            fontSize: token.fontSizeSM,
            fontWeight: token.fontWeightStrong,
          }}
        >
          {group ? <TeamOutlined /> : initials(name)}
        </Avatar>
      </span>
    </Tooltip>
  );
}

/**
 * A date-only deadline as the prototype draws it: time left first, red with
 * a clock inside a day or once passed, amber inside two days, plain beyond;
 * the day itself under it. The words carry the urgency, the colour repeats it.
 */
export function DueText({
  day,
  now,
  done = false,
}: {
  day: string;
  now: number;
  /** A finished case shows the day only. */
  done?: boolean;
}) {
  const { token } = theme.useToken();
  const deadline = dayDeadline(day, now);
  if (!deadline) return <span>{UNKNOWN_TIME}</span>;
  const colour =
    deadline.overdue || deadline.leftMs < 24 * HOUR
      ? token.colorErrorText
      : deadline.leftMs < 48 * HOUR
        ? token.colorWarningText
        : undefined;
  return (
    <span className="flex flex-col items-end text-end">
      {done ? null : (
        <Typography.Text
          strong={!!colour}
          style={colour ? { color: colour } : undefined}
        >
          {colour ? <ClockCircleOutlined aria-hidden className="me-1" /> : null}
          {deadline.relative}
        </Typography.Text>
      )}
      <Typography.Text type={done ? undefined : "secondary"}>
        {deadline.absolute}
      </Typography.Text>
    </span>
  );
}

/**
 * The footer every list ends with: where the list stands. Every list is loaded
 * whole, so the search runs over all of it; a tab shows a part on purpose.
 */
export function listFooter(
  shown: number,
  inTab: number,
  total: number,
  noun: string,
  searching: boolean,
): string {
  if (searching)
    return `${shown}/${inTab} ${noun} khớp bộ lọc · đã tải đủ ${total} ${noun}`;
  if (inTab < total)
    return `${inTab} ${noun} trong nhóm này · đã tải đủ ${total} ${noun}`;
  return `Đã hiện đủ ${total} ${noun}`;
}

// ------------------------------------------------- activity filter chip --

/**
 * "Lọc theo hoạt động DW1": the list narrowed to the cases a count on the
 * activity page stands for, said in words, and "Xóa" to see them all.
 */
export function ActivityFilterChip({
  filter,
  onClear,
}: {
  filter: CaseListActivity;
  onClear: () => void;
}) {
  const words = describeActivity(filter);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="small"
        icon={<CloseOutlined aria-hidden />}
        iconPlacement="end"
        className="h-auto! whitespace-normal! text-start"
        aria-label={`Bỏ lọc theo hoạt động DW1: ${words}`}
        onClick={onClear}
      >
        Lọc theo hoạt động DW1: {words}
      </Button>
      <Button size="small" type="link" onClick={onClear}>
        Xóa
      </Button>
    </div>
  );
}
