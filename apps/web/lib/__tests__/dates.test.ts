import { afterEach, describe, expect, it } from "vitest";
import {
  formatDate,
  formatDateTime,
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

  it("refuses a date and time with no offset instead of reading it in this zone", () => {
    process.env.TZ = zone;
    for (const value of ["2026-10-14T09:00:00", "2026-10-14 09:00"]) {
      expect(formatDateTime(value)).toBe(UNKNOWN_TIME);
      expect(formatDate(value)).toBe(UNKNOWN_TIME);
    }
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
