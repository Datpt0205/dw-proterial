import type { SalesSchemas } from "@dw/api-client";
import { intentKindLabel } from "./labels";
import { messageRef } from "./messages";
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

type TriggerReplay = NonNullable<SkillReplay["trigger"]>;

/** How one side of a replay read the taught mail, in words. */
function readAs(
  kind?: string | null,
  label?: string | null,
  route?: string | null,
) {
  if (route == null) return "mô hình không trả lời";
  if (!kind) return "không nhận ra loại thư";
  return `“${intentKindLabel({ kind, kind_label: label })}”`;
}

/**
 * The mail a version was taught from (ticket 34), read with it and without
 * it; null for a version no triage card proposed.
 */
export function triggerLine(replay: SkillReplay): string | null {
  const taught: TriggerReplay | null | undefined = replay.trigger;
  if (!taught) return null;
  const ref = messageRef(taught.message_id);
  if (!taught.found)
    return `Thư gốc ${ref}: không còn trong hộp thư, không chạy thử được`;
  return `Thư gốc ${ref}: bản đề xuất đọc là ${readAs(taught.with_kind, taught.with_label, taught.with_route)} · bản đang dùng đọc là ${readAs(taught.without_kind, taught.without_label, taught.without_route)}`;
}
