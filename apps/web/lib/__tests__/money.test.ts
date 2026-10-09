import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CURRENCIES,
  formatAmountInput,
  formatMoney,
  formatMoneyShort,
  formatQuantity,
  moneyInWords,
  parseAmountInput,
  type Currency,
} from "../money";

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

describe("formatMoney in every currency the API names", () => {
  // The owner of the enum is the OpenAPI snapshot the client is generated from.
  const spec = JSON.parse(
    readFileSync(
      resolve(__dirname, "../../../../contracts/openapi/openapi.json"),
      "utf8",
    ),
  ) as {
    components: {
      schemas: Record<
        string,
        { properties?: Record<string, { enum?: string[] }> }
      >;
    };
  };
  const enumerated =
    spec.components.schemas.OrderCaseView!.properties!.currency!.enum!;

  it("formats each currency in the OpenAPI enum, and no other", () => {
    expect(enumerated.length).toBeGreaterThan(0);
    expect([...CURRENCIES].sort()).toEqual([...enumerated].sort());
    for (const currency of enumerated) {
      const text = formatMoney(1234.5, currency as Currency);
      expect(text).toMatch(/^1\.234,5/);
      expect(text).not.toMatch(/₫|¥|\$/);
    }
  });

  it("writes yen with grouping and 'JPY', keeping a fraction instead of rounding it", () => {
    expect(formatMoney(12300, "JPY")).toBe(`12.300${NBSP}JPY`);
    expect(formatMoney("0.65", "JPY")).toBe(`0,65${NBSP}JPY`);
  });

  it("takes the API's decimal strings as they are", () => {
    expect(formatMoney("94115000", "VND")).toBe(`94.115.000${NBSP}đ`);
    // USD always shows cents, and up to four decimals of a unit price.
    expect(formatMoney("0.6150", "USD")).toBe(`0,615${NBSP}USD`);
  });
});

describe("formatQuantity", () => {
  it("groups the Vietnamese way with a decimal comma", () => {
    expect(formatQuantity("6100")).toBe("6.100");
    expect(formatQuantity("12.5")).toBe("12,5");
  });
});

describe("parseAmountInput", () => {
  it.each([
    ["18.450.000.000", "18450000000"],
    ["18,450,000,000", "18450000000"],
    ["18450000000 đ", "18450000000"],
    ["12,5", "12.5"],
    ["0.6150", "0.6150"],
    ["0,615", "0.615"],
    ["1.150", "1150"],
    ["1.234,50", "1234.50"],
    ["1,234.50", "1234.50"],
  ])("reads %s as %s", (text, value) => {
    expect(parseAmountInput(text)).toBe(value);
  });

  it.each(["1.2.3", "abc", "", "1.23.456", "12-3"])(
    "refuses %j rather than guessing",
    (text) => {
      expect(parseAmountInput(text)).toBeNull();
    },
  );

  it("writes a decimal string back with grouping and a decimal comma", () => {
    expect(formatAmountInput("18450000000")).toBe("18.450.000.000");
    expect(formatAmountInput("0.615")).toBe("0,615");
  });
});

describe("formatMoneyShort", () => {
  it("shortens to tỷ, and is no good for a threshold", () => {
    expect(formatMoneyShort(18450000000)).toBe(`18,45${NBSP}tỷ`);
    expect(formatMoneyShort(14995000000)).toBe(formatMoneyShort(15000000000));
  });
});

describe("moneyInWords (Bằng chữ)", () => {
  it.each([
    [0, "Không đồng"],
    [5, "Năm đồng"],
    [15, "Mười lăm đồng"],
    [21, "Hai mươi mốt đồng"],
    [105, "Một trăm linh năm đồng"],
    [1050, "Một nghìn không trăm năm mươi đồng"],
    [1005000, "Một triệu không trăm linh năm nghìn đồng"],
    [1285000, "Một triệu hai trăm tám mươi lăm nghìn đồng"],
    [18450000000, "Mười tám tỷ bốn trăm năm mươi triệu đồng"],
    [1000000000000, "Một nghìn tỷ đồng"],
    [1234000000000, "Một nghìn hai trăm ba mươi bốn tỷ đồng"],
    [2000000005, "Hai tỷ không trăm linh năm đồng"],
    [-5000, "Âm năm nghìn đồng"],
  ])("%d reads %j", (amount, words) => {
    expect(moneyInWords(amount)).toBe(words);
  });

  it("refuses a fraction rather than rounding it", () => {
    expect(() => moneyInWords(1.5)).toThrow(RangeError);
  });
});
