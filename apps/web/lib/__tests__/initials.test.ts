import { describe, expect, it } from "vitest";
import { initials } from "../initials";

describe("an avatar's initials", () => {
  it.each([
    ["Nguyễn Văn An", "NA"],
    ["Nguyễn Văn An (bạn)", "NA"],
    ["Đỗ Trường Giang", "ĐG"],
    ["DW1", "D"],
    ["(PIC)", "?"],
    ["", "?"],
  ])("%j → %j", (name, expected) => {
    expect(initials(name)).toBe(expected);
  });
});
