import { describe, expect, it } from "vitest";
import { compareVi, fold, matches } from "../search";

describe("a list search", () => {
  it.each([
    ["ha noi", "Công ty Hà Nội"],
    ["HA NOI", "công ty hà nội"],
    ["dien", "Điện lực"],
    ["d", "Đỗ Trường Giang"],
    ["vlx 0118", "PO VLX-PO-2609-0118"],
  ])("finds %j in %j", (query, text) => {
    expect(matches(query, [text])).toBe(true);
  });

  it("needs every word, in any of the fields", () => {
    expect(matches("vlx giang", ["VLX-PO-1", "Đỗ Trường Giang"])).toBe(true);
    expect(matches("vlx khoa", ["VLX-PO-1", "Đỗ Trường Giang"])).toBe(false);
  });

  it("matches everything when nothing is typed, and skips missing fields", () => {
    expect(matches("  ", ["x"])).toBe(true);
    expect(matches("x", [null, undefined, "x"])).toBe(true);
  });

  it("folds marks and đ", () => {
    expect(fold("Đơn hàng Bảo")).toBe("don hang bao");
  });
});

describe("a Vietnamese sort", () => {
  it("puts Đ after D and before E, not after Z", () => {
    const names = ["Zeta", "Đỗ", "Dung", "Em"];
    expect([...names].sort(compareVi)).toEqual(["Dung", "Đỗ", "Em", "Zeta"]);
  });

  it("orders numbers inside codes by value", () => {
    expect(["PO-10", "PO-9"].sort(compareVi)).toEqual(["PO-9", "PO-10"]);
  });
});
