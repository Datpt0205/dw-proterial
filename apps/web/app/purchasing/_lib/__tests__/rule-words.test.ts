// @vitest-environment node
import { describe, expect, it } from "vitest";
import { changesInWords, pathName } from "../rule-words";

const RULES = {
  policy_id: "purchasing_rules",
  policy_version: "1.5.0",
  pr_form: {
    required: ["budget_code"],
    max_lines: 50,
    currencies: ["VND", "USD"],
  },
  approval: {
    currency: "VND",
    tiers: [
      {
        up_to: "20000000",
        scope: "purchasing.approve.tier1",
        label: "Trưởng phòng Mua hàng",
      },
      {
        up_to: null,
        scope: "purchasing.approve.tier3",
        label: "Tổng giám đốc",
      },
    ],
    escalate: ["over_budget"],
  },
};

/**
 * The settings page shows a change as words a person reads, never a field
 * code: each path it names, each value in the unit the rule holds it in.
 */
describe("a rule change in words", () => {
  it("names the tier and its limit in money, a tier without a limit as unlimited", () => {
    const after = structuredClone(RULES);
    after.policy_version = "1.5.1";
    after.approval.tiers[0]!.up_to = "50000000";
    after.approval.tiers[1]!.up_to = "900000000";
    expect(changesInWords(RULES, after)).toEqual([
      {
        path: "approval.tiers.0.up_to",
        name: "Bậc duyệt 1 · Hạn mức đến",
        before: "20.000.000 đ",
        after: "50.000.000 đ",
      },
      {
        path: "approval.tiers.1.up_to",
        name: "Bậc duyệt 2 · Hạn mức đến",
        before: "không giới hạn",
        after: "900.000.000 đ",
      },
    ]);
  });

  it("names how long stored mail is kept, in days", () => {
    expect(pathName("retention.mailbox_days")).toBe("Lưu trữ · Thư đã lưu");
  });

  it("reads a list of codes in the glossary's words", () => {
    const after = structuredClone(RULES);
    after.approval.escalate = ["over_budget", "budget_unknown"];
    after.pr_form.required = [];
    const words = changesInWords(RULES, after);
    expect(words.map((c) => [c.name, c.after])).toEqual([
      ["Yêu cầu mua hàng · Thông tin bắt buộc", "không có"],
      [
        "Duyệt · Phát hiện đưa thẳng lên bậc cuối",
        "vượt ngân sách còn lại, mã ngân sách không có",
      ],
    ]);
  });

  it("says a switch's level, and never drops a path it cannot name", () => {
    const words = changesInWords(
      { steps: { rfq: "ai_review" }, extra: 1 },
      { steps: { rfq: "person" }, extra: 2 },
    );
    expect(words.map((c) => [c.name, c.before, c.after])).toEqual([
      ["Công tắc · Soạn thư hỏi giá", "AI làm, người duyệt", "Người làm"],
      ["Một mục khác của quy tắc", "1", "2"],
    ]);
    expect(pathName("approval.tiers.2.label")).toBe(
      "Bậc duyệt 3 · Người duyệt",
    );
  });
});

describe("a refused draft in words", () => {
  it("names the part of the rule, never the code or the model's words", async () => {
    const { problemWords } = await import("../rule-words");
    expect(problemWords("path_unknown:approver")).toBe(
      "DW2 muốn đổi một mục quy tắc không có, nên không có bản nháp.",
    );
    expect(problemWords("digit_invented:rfq.reply_days")).toContain(
      "(Hỏi giá · Thời gian chờ trả lời)",
    );
    expect(problemWords("document_invalid")).not.toMatch(/[a-z]+_[a-z]+/);
    expect(problemWords("something_new:x.y")).toBe(
      "Bản nháp không qua được kiểm tra của quy tắc.",
    );
  });
});
