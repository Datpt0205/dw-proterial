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
