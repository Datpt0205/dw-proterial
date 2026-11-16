import { describe, expect, it } from "vitest";
import {
  incompleteLine,
  nextSkillVersion,
  replayLine,
  securityLine,
  triggerLine,
  type Skill,
  type SkillReplay,
  type SkillVersion,
} from "../skills";

const SKILL: Skill = {
  name: "thread-intents",
  ref: "sales_skill_thread_intents@1.0.0",
  platform_ref: "sales_skill_thread_intents@1.0.0",
  layer: "platform",
  description: "Reading a thread message's intents.",
  instructions: "Say what the message does.",
};

function version(ref: string, name = "thread-intents"): SkillVersion {
  return {
    version_id: ref,
    name,
    ref,
    status: "rejected",
    proposed_by: "00000000-0000-0000-0000-000000000001",
    decided_by: null,
    description: "d",
    instructions: "i",
    approval_id: null,
    replay: null,
  };
}

const REPLAY: SkillReplay = {
  version_id: "v",
  replayed_at: "2026-11-16T02:00:00Z",
  source: "platform_examples",
  outcome: "replayed",
  messages: 60,
  right_with: 50,
  right_without: 48,
  unanswered: 0,
  security_failed: [],
};

describe("skills", () => {
  it("offers a number above every one the skill used, its own skill's only", () => {
    expect(nextSkillVersion(SKILL, [])).toBe("1.0.1");
    const used = [
      version("sales_skill_thread_intents@1.3.0"),
      version("sales_skill_other@9.0.0", "other"),
    ];
    expect(nextSkillVersion(SKILL, used)).toBe("1.3.1");
  });

  it("says the replay in one line, and what is wrong plainly", () => {
    expect(replayLine(REPLAY)).toBe(
      "Đúng 50/60 với bản đề xuất · 48/60 với bản đang dùng",
    );
    expect(securityLine(REPLAY)).toBeNull();
    expect(incompleteLine(REPLAY)).toBeNull();
    const bad = {
      ...REPLAY,
      outcome: "incomplete" as const,
      unanswered: 3,
      security_failed: ["INJ2", "RP31"],
    };
    expect(securityLine(bad)).toBe(
      'Bản đề xuất trượt 2 ca bảo mật (đọc thành "đồng ý" một thư không đồng ý): INJ2, RP31',
    );
    expect(incompleteLine(bad)).toBe(
      "3 lần mô hình không trả lời: kết quả chưa đủ",
    );
  });

  it("says how each side read the mail a version was taught from (ticket 34)", () => {
    expect(triggerLine(REPLAY)).toBeNull();
    const taught = {
      ...REPLAY,
      trigger: {
        message_id: "M31",
        found: true,
        with_kind: "invoice_request",
        with_label: "Khách hỏi hoá đơn",
        with_route: "other" as const,
        without_kind: "other",
        without_label: null,
        without_route: "other" as const,
      },
    };
    expect(triggerLine(taught)).toBe(
      "Thư gốc M31: bản đề xuất đọc là “Khách hỏi hoá đơn” · bản đang dùng đọc là “Khác”",
    );
    const gone = { ...taught, trigger: { ...taught.trigger, found: false } };
    expect(triggerLine(gone)).toBe(
      "Thư gốc M31: không còn trong hộp thư, không chạy thử được",
    );
  });
});
