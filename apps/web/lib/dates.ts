import dayjs from "dayjs";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";

/**
 * The one place a date is turned into text for the screen.
 *
 * Every instant is shown in Vietnam's time, whatever the viewer's machine is
 * set to: a deadline read in Los Angeles must name the same day it names in
 * Hà Nội. DD/MM/YYYY with a 24-hour clock, written out rather than left to
 * `Intl`, because the order and the clock are the requirement, not a locale
 * preference.
 */

dayjs.extend(utc);
dayjs.extend(timezone);

export const VN_TIME_ZONE = "Asia/Ho_Chi_Minh";

function inVietnam(iso: string) {
  return dayjs.utc(iso).tz(VN_TIME_ZONE);
}

/** "DD/MM/YYYY" in Vietnam's calendar, or an em dash when there is no date. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return inVietnam(iso).format("DD/MM/YYYY");
}

/** "DD/MM/YYYY HH:mm" in Vietnam's time, or an em dash when there is no date. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return inVietnam(iso).format("DD/MM/YYYY HH:mm");
}
