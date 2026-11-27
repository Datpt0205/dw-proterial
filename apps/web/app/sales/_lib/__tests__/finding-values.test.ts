import { describe, expect, it } from "vitest";
import { findingValueWords } from "../finding-values";

// Each value as the server writes it: `order_checks._compliance_finding`
// (the strings `test_order_intake.py` asserts), `quotes._basis_mismatch`,
// `quotes._unknown_floor_factors` and the price comparisons in `quotes.py`.
describe("a finding's values in words (full review, 2026-11-27)", () => {
  it.each([
    [
      "missing_noc_esf",
      "NOC confirmed, ESF FY2026, denial-list check within 90 days",
      "NOC đã xác nhận, ESF năm tài chính 2026, kiểm danh sách cấm trong 90 ngày",
    ],
    [
      "missing_noc_esf",
      "no NOC, ESF FY2025, denial-list check 2026-09-01",
      "chưa có NOC, ESF năm tài chính 2025, kiểm danh sách cấm ngày 01/09/2026",
    ],
    [
      "missing_noc_esf",
      "NOC confirmed, no ESF, no denial-list check",
      "NOC đã xác nhận, chưa có ESF, chưa kiểm danh sách cấm",
    ],
    ["customer_temporary", "official", "Khách chính thức"],
    ["customer_temporary", "temporary", "Khách tạm"],
    ["price_basis_mismatch", "lme_band", "Theo dải LME"],
    ["price_basis_mismatch", "fixed", "Cố định"],
    [
      "price_basis_mismatch",
      "10500-11000 @2026-09",
      "10.500–11.000 USD/tấn · LME tháng 09/2026",
    ],
    ["price_basis_mismatch", "@2026-10", "LME tháng 10/2026"],
    [
      "price_basis_mismatch",
      "none @2026-09",
      "Không có dải · LME tháng 09/2026",
    ],
    ["price_floor_unknown", "floor", "Giá sàn tính được"],
    [
      "price_floor_unknown",
      "copper_weight,lme",
      "thiếu khối lượng đồng, thiếu giá LME",
    ],
    ["above_target_price", "<= 0.65", "≤ 0,65"],
    ["above_target_price", "0.7050", "0,705"],
    ["price_below_policy_floor", ">= 1.2345", "≥ 1,2345"],
  ])("%s: %s", (code, value, words) => {
    expect(findingValueWords(code, value)).toBe(words);
  });

  it.each([
    // A shape it does not know shows as written, never half read.
    ["missing_noc_esf", "NOC confirmed, something new"],
    ["price_basis_mismatch", "lme_band,fixed,other"],
    // Another code's number is an identifier or a count, untouched.
    ["duplicate_po", "4500012345"],
    ["quotation_missing", "valid on 2026-09-23"],
  ])("%s keeps %s as written", (code, value) => {
    expect(findingValueWords(code, value)).toBe(value);
  });
});
