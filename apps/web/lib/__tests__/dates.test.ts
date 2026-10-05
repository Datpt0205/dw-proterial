import { afterEach, describe, expect, it } from "vitest";
import {
  dayDeadline,
  daysSince,
  formatAge,
  formatDate,
  formatDateTime,
  formatDuration,
  formatInstant,
  formatMonth,
  fromPickerDay,
  toPickerDay,
  TIME_ZONE_LABEL,
  UNKNOWN_TIME,
} from "../dates";

// The zone this process runs in stands for the browser's. Node rereads it when
// it changes, so each case can sit in a zone of its own.
const ORIGINAL_TZ = process.env.TZ;
afterEach(() => {
  process.env.TZ = ORIGINAL_TZ;
});

const BROWSER_ZONES = ["UTC", "America/Los_Angeles", "Asia/Tokyo"];

describe.each(BROWSER_ZONES)("in a browser set to %s", (zone) => {
  it("shows an instant in Vietnam, time first, with the zone", () => {
    process.env.TZ = zone;
    expect(formatDateTime("2026-10-14T02:00:00Z")).toBe(
      "09:00 14/10/2026 (giờ Việt Nam)",
    );
    expect(formatDateTime("2026-10-14T09:00:00+07:00")).toBe(
      "09:00 14/10/2026 (giờ Việt Nam)",
    );
    // The API's own forms: microseconds, and an offset west of UTC.
    expect(formatDateTime("2026-10-14T02:00:00.123456Z")).toBe(
      "09:00 14/10/2026 (giờ Việt Nam)",
    );
    expect(formatDateTime("2026-10-13T19:00:00-07:00")).toBe(
      "09:00 14/10/2026 (giờ Việt Nam)",
    );
  });

  it("takes the calendar day an instant falls on in Vietnam", () => {
    process.env.TZ = zone;
    // 20:00 UTC on the 14th is 03:00 on the 15th in Vietnam.
    expect(formatDate("2026-10-14T20:00:00Z")).toBe("15/10/2026");
  });

  it("keeps a date-only value on its own calendar day, never its midnight", () => {
    process.env.TZ = zone;
    expect(formatDate("2026-10-14")).toBe("14/10/2026");
    expect(formatDateTime("2026-10-14")).toBe("14/10/2026");
  });

  it("runs a date-only deadline to the end of its day in Vietnam", () => {
    process.env.TZ = zone;
    // 23:30 on the 7th in Vietnam: the 7th is still due, with 30 minutes left.
    const late = Date.parse("2026-10-07T16:30:00Z");
    const deadline = dayDeadline("2026-10-07", late)!;
    expect(deadline.absolute).toBe("hết ngày 07/10/2026");
    expect(deadline.withZone).toBe("hết ngày 07/10/2026 (giờ Việt Nam)");
    expect(deadline.overdue).toBe(false);
    expect(deadline.relative).toBe("còn 30 phút");
    // 00:30 on the 8th in Vietnam: thirty minutes overdue.
    const next = dayDeadline("2026-10-07", Date.parse("2026-10-07T17:30:00Z"))!;
    expect(next.overdue).toBe(true);
    expect(next.relative).toBe("quá hạn 30 phút");
  });

  it("counts calendar days in Vietnam and keeps a picked day on its own date", () => {
    process.env.TZ = zone;
    expect(daysSince("2026-10-01", Date.parse("2026-10-05T01:00:00Z"))).toBe(4);
    expect(fromPickerDay(toPickerDay("2026-11-16"))).toBe("2026-11-16");
    expect(formatInstant(Date.parse("2026-10-14T02:00:00Z"))).toBe(
      "09:00 14/10/2026 (giờ Việt Nam)",
    );
  });

  it("refuses a date and time with no offset instead of reading it in this zone", () => {
    process.env.TZ = zone;
    for (const value of ["2026-10-14T09:00:00", "2026-10-14 09:00"]) {
      expect(formatDateTime(value)).toBe(UNKNOWN_TIME);
      expect(formatDate(value)).toBe(UNKNOWN_TIME);
    }
  });
});

describe("durations", () => {
  it("names the two largest units", () => {
    expect(formatDuration(30_000)).toBe("dưới 1 phút");
    expect(formatDuration(12 * 60_000)).toBe("12 phút");
    expect(formatDuration((5 * 60 + 12) * 60_000)).toBe("5 giờ 12 phút");
    expect(formatDuration((3 * 24 + 4) * 3_600_000 + 5 * 60_000)).toBe(
      "3 ngày 4 giờ",
    );
    expect(formatDuration(2 * 24 * 3_600_000)).toBe("2 ngày");
  });

  it("reads an unknown or negative span as unknown, never as zero", () => {
    expect(formatDuration(null)).toBe(UNKNOWN_TIME);
    expect(formatDuration(-1)).toBe(UNKNOWN_TIME);
    expect(formatAge("not a date", Date.now())).toBe(UNKNOWN_TIME);
    expect(dayDeadline(null, Date.now())).toBeNull();
    expect(dayDeadline("2026-02-30", Date.now())).toBeNull();
  });

  it("writes the API's month as mm/yyyy", () => {
    expect(formatMonth("2026-09")).toBe("09/2026");
    expect(formatMonth("2026-13")).toBe(UNKNOWN_TIME);
  });
});

describe("dates", () => {
  it("leaves the zone off only when asked, for a header that carries it", () => {
    expect(formatDateTime("2026-10-14T02:00:00Z", { zoneLabel: false })).toBe(
      "09:00 14/10/2026",
    );
    expect(TIME_ZONE_LABEL).toBe("giờ Việt Nam");
  });

  it("shows a missing or unreadable value as unknown, never as a dash", () => {
    const unreadable = [null, undefined, "", "not a date", "2026-13-45"];
    // An impossible day is unreadable, not rolled over into the next month,
    // whether it stands alone or carries a time.
    for (const value of [...unreadable, "2026-02-30", "2026-02-30T00:00:00Z"]) {
      expect(formatDate(value)).toBe(UNKNOWN_TIME);
      expect(formatDateTime(value)).toBe(UNKNOWN_TIME);
    }
    expect(UNKNOWN_TIME).not.toBe("—");
  });
});
