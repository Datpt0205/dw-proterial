import dayjs, { type Dayjs } from "dayjs";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";
import "dayjs/locale/vi";

/**
 * The one place a date or a time is turned into text for the screen, and the
 * one place dayjs is set up (antd's pickers read its global locale).
 *
 * Every time is shown in Vietnam, whatever zone the browser is in: the people
 * using this work to Vietnamese deadlines, and a laptop set to another zone
 * must not move them. Time comes first ("09:00 14/10/2026"), the way the
 * briefs write it, with "giờ Việt Nam" on the value unless a column header
 * already says it. A value that is missing or unreadable is shown as unknown,
 * never as "—", which reads as "there is none".
 */
dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.locale("vi");

const TIME_ZONE = "Asia/Ho_Chi_Minh";
/** For a column header, when the cells leave the zone off. */
export const TIME_ZONE_LABEL = "giờ Việt Nam";
/** What a missing or unreadable date or time reads as. */
export const UNKNOWN_TIME = "Không rõ";

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
/**
 * An instant as the API writes it: a date, a time, and the offset that puts it
 * on the clock ("Z" or "+07:00"), the one form every browser reads alike.
 */
const INSTANT =
  /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/;

/**
 * The calendar day `value` names, in Vietnam. dayjs and `Date` both roll an
 * impossible day over ("2026-02-30" would become 2 March), so a day counts
 * only if it reads back exactly as written.
 */
function calendarDay(value: string): Dayjs | null {
  const day = dayjs.tz(value, TIME_ZONE);
  return day.isValid() && day.format("YYYY-MM-DD") === value ? day : null;
}

/**
 * A date-only value is a calendar day and is read as that day in Vietnam. It
 * never goes through `new Date()`, which reads it as UTC midnight: one day
 * early west of UTC. An instant is shown in Vietnam. A date and time with no
 * offset is neither: the browser would read it in its own zone, so two laptops
 * would show two times, and it is unreadable rather than guessed.
 */
function inVietnam(value: string | null | undefined): Dayjs | null {
  if (!value) return null;
  if (DATE_ONLY.test(value)) return calendarDay(value);
  const instant = INSTANT.exec(value);
  if (!instant || !calendarDay(instant[1]!)) return null;
  const time = dayjs(value).tz(TIME_ZONE);
  return time.isValid() ? time : null;
}

/** "14/10/2026": the calendar day in Vietnam. */
export function formatDate(value: string | null | undefined): string {
  return inVietnam(value)?.format("DD/MM/YYYY") ?? UNKNOWN_TIME;
}

/**
 * "09:00 14/10/2026 (giờ Việt Nam)". Pass `{ zoneLabel: false }` only where a
 * column header carries `TIME_ZONE_LABEL` for every cell under it. A date-only
 * value has no time to show: it is "14/10/2026", the day, never its midnight,
 * which would read as a deadline at the start of the day it names.
 */
export function formatDateTime(
  value: string | null | undefined,
  { zoneLabel = true }: { zoneLabel?: boolean } = {},
): string {
  if (value && DATE_ONLY.test(value)) return formatDate(value);
  const time = inVietnam(value);
  if (!time) return UNKNOWN_TIME;
  const text = time.format("HH:mm DD/MM/YYYY");
  return zoneLabel ? `${text} (${TIME_ZONE_LABEL})` : text;
}

// ------------------------------------------------- durations and deadlines --

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * "3 ngày 4 giờ", "5 giờ 12 phút", "12 phút", "dưới 1 phút": the two largest
 * units, so a wait reads at a glance. A negative or missing span is unknown.
 */
export function formatDuration(
  milliseconds: number | null | undefined,
): string {
  if (
    milliseconds == null ||
    !Number.isFinite(milliseconds) ||
    milliseconds < 0
  )
    return UNKNOWN_TIME;
  if (milliseconds < MINUTE) return "dưới 1 phút";
  const days = Math.floor(milliseconds / DAY);
  const hours = Math.floor((milliseconds % DAY) / HOUR);
  const minutes = Math.floor((milliseconds % HOUR) / MINUTE);
  if (days > 0) return hours > 0 ? `${days} ngày ${hours} giờ` : `${days} ngày`;
  if (hours > 0)
    return minutes > 0 ? `${hours} giờ ${minutes} phút` : `${hours} giờ`;
  return `${minutes} phút`;
}

/** The instant `value` names, in milliseconds; null when it names none. */
export function instantMs(value: string | null | undefined): number | null {
  if (!value || DATE_ONLY.test(value)) return null;
  return inVietnam(value)?.valueOf() ?? null;
}

/** An instant held as milliseconds (a clock reading), formatted like the rest. */
export function formatInstant(
  milliseconds: number,
  options: { zoneLabel?: boolean } = {},
): string {
  return formatDateTime(dayjs(milliseconds).toISOString(), options);
}

/** How long ago `value` was, against `now` (milliseconds): "3 ngày 4 giờ". */
export function formatAge(
  value: string | null | undefined,
  now: number,
): string {
  const at = instantMs(value);
  return at === null ? UNKNOWN_TIME : formatDuration(Math.max(0, now - at));
}

export interface Deadline {
  /** "hết ngày 07/10/2026": the last day included; the zone goes in the
   * column header or in `withZone`. */
  absolute: string;
  /** "hết ngày 07/10/2026 (giờ Việt Nam)". */
  withZone: string;
  /** "còn 2 ngày 4 giờ" or "quá hạn 1 ngày 2 giờ". */
  relative: string;
  overdue: boolean;
  /** Milliseconds left (negative once passed), for ordering and tone. */
  leftMs: number;
}

/**
 * A date-only deadline is a calendar day: it runs to the end of that day in
 * Vietnam, so the day itself is never shown as already overdue at its own
 * midnight. Null when the day is missing or unreadable, which the screen draws
 * as unknown, never as "no deadline".
 */
export function dayDeadline(
  day: string | null | undefined,
  now: number,
): Deadline | null {
  if (!day || !DATE_ONLY.test(day)) return null;
  const start = calendarDay(day);
  if (!start) return null;
  const end = start.add(1, "day").valueOf();
  const leftMs = end - now;
  const overdue = leftMs <= 0;
  const absolute = `hết ngày ${start.format("DD/MM/YYYY")}`;
  return {
    absolute,
    withZone: `${absolute} (${TIME_ZONE_LABEL})`,
    relative: overdue
      ? `quá hạn ${formatDuration(-leftMs)}`
      : `còn ${formatDuration(leftMs)}`,
    overdue,
    leftMs,
  };
}

/** Whole calendar days in Vietnam from `day` to `now` (0 on the day itself). */
export function daysSince(
  day: string | null | undefined,
  now: number,
): number | null {
  if (!day || !DATE_ONLY.test(day)) return null;
  const start = calendarDay(day);
  if (!start) return null;
  const today = dayjs(now).tz(TIME_ZONE).startOf("day");
  return Math.round((today.valueOf() - start.valueOf()) / DAY);
}

/** "09/2026" for the API's "2026-09"; unknown for anything else. */
export function formatMonth(month: string | null | undefined): string {
  const parts = month ? /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month) : null;
  return parts ? `${parts[2]}/${parts[1]}` : UNKNOWN_TIME;
}

/** "14/10": a day inside a range whose year is said elsewhere. */
export function formatDayMonth(value: string | null | undefined): string {
  return inVietnam(value)?.format("DD/MM") ?? UNKNOWN_TIME;
}

/**
 * A date-only value as the value antd's `DatePicker` holds, on its own day in
 * Vietnam whatever zone the browser is in; `fromPickerDay` turns the picked
 * day back into "YYYY-MM-DD" without passing through `toISOString()`.
 */
export function toPickerDay(day: string | null | undefined): Dayjs | null {
  return day && DATE_ONLY.test(day) ? calendarDay(day) : null;
}

export function fromPickerDay(value: Dayjs | null | undefined): string | null {
  return value ? value.format("YYYY-MM-DD") : null;
}
