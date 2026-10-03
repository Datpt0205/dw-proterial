import { describe, expect, it } from "vitest";
import { formatMoney } from "../money";

// The space before the unit is a no-break space.
const NBSP = "\u00a0";

describe("formatMoney", () => {
  it("writes dong with Vietnamese grouping and 'đ', not '₫'", () => {
    expect(formatMoney(18_450_000_000, "VND")).toBe(`18.450.000.000${NBSP}đ`);
    expect(formatMoney(0, "VND")).toBe(`0${NBSP}đ`);
    expect(formatMoney(-125_400, "VND")).toBe(`-125.400${NBSP}đ`);
    expect(formatMoney(1, "VND")).not.toContain("₫");
  });

  it("shows the decimals a dong amount carries instead of rounding them off", () => {
    expect(formatMoney(15_230.5, "VND")).toBe(`15.230,5${NBSP}đ`);
  });

  it("writes dollars with a decimal comma, cents always, and 'USD'", () => {
    expect(formatMoney(1234.5, "USD")).toBe(`1.234,50${NBSP}USD`);
    expect(formatMoney(12, "USD")).toBe(`12,00${NBSP}USD`);
  });

  it("keeps a unit price below a cent", () => {
    expect(formatMoney(2.3456, "USD")).toBe(`2,3456${NBSP}USD`);
  });
});
