"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ClockCircleOutlined,
  RightOutlined,
  SearchOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Card,
  Input,
  Segmented,
  Select,
  theme,
  Tooltip,
  Typography,
} from "antd";
import { STATUS_TONES, type StatusTone } from "@dw/ui";
import { dayDeadline, UNKNOWN_TIME } from "../../../lib/dates";
import { initials } from "../../../lib/initials";

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

/**
 * The row's two lines: its name, which is the link (opens in a new tab,
 * truncated with the whole on hover), over its identifier in monospace and
 * whatever else identifies it. An identifier is never truncated.
 */
export function RowTitle({
  href,
  title,
  code,
  sub,
}: {
  href: string;
  title: string;
  code?: string | null;
  sub?: ReactNode;
}) {
  const { token } = theme.useToken();
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
