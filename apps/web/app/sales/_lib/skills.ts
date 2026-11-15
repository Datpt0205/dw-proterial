import type { SalesSchemas } from "@dw/api-client";
import { nextVersion } from "./rules";

export type SkillsView = SalesSchemas["SkillsView"];
export type Skill = SalesSchemas["SkillView"];
export type SkillVersion = SalesSchemas["SkillVersionView"];
export type SkillReplay = SalesSchemas["SkillReplay"];

/** Where a skill in force comes from, in the rules page's words. */
export const SKILL_LAYER: Record<Skill["layer"], string> = {
  platform: "Của nền tảng",
  tenant: "Riêng của công ty",
};

/**
 * The number a new version of ``skill`` is offered: one patch above every
 * number it has used, the platform's and the company's, since the server
 * refuses a number already used (the rules' own `nextVersion`).
 */
export function nextSkillVersion(
  skill: Skill,
  versions: readonly SkillVersion[],
): string {
  return nextVersion([
    skill.ref,
    skill.platform_ref,
    ...versions.filter((v) => v.name === skill.name).map((v) => v.ref),
  ]).replace(/^.*@/, "");
}

/** The versions of ``skill``, as listed (newest first by the server). */
export function versionsOf(
  skill: Skill,
  versions: readonly SkillVersion[],
): SkillVersion[] {
  return versions.filter((v) => v.name === skill.name);
}

/** A replay in one line: "Đúng 50/60 với bản đề xuất · 48/60 với bản đang dùng". */
export function replayLine(replay: SkillReplay): string {
  const n = replay.messages;
  return `Đúng ${replay.right_with}/${n} với bản đề xuất · ${replay.right_without}/${n} với bản đang dùng`;
}

/** The security cases a proposal failed, said plainly; null when none. */
export function securityLine(replay: SkillReplay): string | null {
  const failed = replay.security_failed ?? [];
  if (failed.length === 0) return null;
  return `Bản đề xuất trượt ${failed.length} ca bảo mật (đọc thành "đồng ý" một thư không đồng ý): ${failed.join(", ")}`;
}

/** Why the counts are partial, or null when every reading was answered. */
export function incompleteLine(replay: SkillReplay): string | null {
  if (replay.outcome !== "incomplete") return null;
  return `${replay.unanswered} lần mô hình không trả lời: kết quả chưa đủ`;
}
