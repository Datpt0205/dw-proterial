import type { SalesSchemas } from "@dw/api-client";
import { intentKindLabel } from "./labels";
import { messageRef } from "./messages";
import { align } from "./rule-diff";
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

/** A customer's SalesOrder skill (ticket 41): its replay reads the customer's worked pairs. */
export function isCustomerSkill(skill: Pick<Skill, "customer_code">): boolean {
  return skill.customer_code != null;
}

/** The versions of ``skill``, as listed (newest first by the server). */
export function versionsOf(
  skill: Skill,
  versions: readonly SkillVersion[],
): SkillVersion[] {
  return versions.filter((v) => v.name === skill.name);
}

/**
 * A replay in one line: "Đúng 50/60 với bản đề xuất · 48/60 với bản đang
 * dùng"; a customer's SalesOrder skill's (ticket 41) counts the customer's
 * worked pairs instead of mails.
 */
export function replayLine(replay: SkillReplay): string {
  const n = replay.messages;
  if (replay.source !== "customer_pairs")
    return `Đúng ${replay.right_with}/${n} với bản đề xuất · ${replay.right_without}/${n} với bản đang dùng`;
  if (n === 0) return "Khách chưa có cặp ví dụ nào: chưa chạy thử được";
  return `Điền đúng ${replay.right_with}/${n} cặp ví dụ của khách với bản đề xuất · ${replay.right_without}/${n} với bản đang dùng`;
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

/** One line of a version's words against the version in force. */
export type WordsLine =
  | { op: "keep" | "add" | "remove"; text: string }
  /** Unchanged lines left out between two changes, by count. */
  | { op: "skip"; count: number };

/**
 * What a version changes in a skill's words, line by line against the
 * version in force (ticket 40): the lines it adds and drops, aligned as the
 * rules' own diff aligns a list (`align`), each change shown with
 * ``context`` unchanged lines around it and every other unchanged run
 * counted, not drawn. Empty where the words are the same.
 */
export function wordsChanges(
  before: string,
  after: string,
  context = 2,
): WordsLine[] {
  const b = before.split(/\r?\n/);
  const a = after.split(/\r?\n/);
  const lines = align(b, a, (x, y) => x === y).map((s) => ({
    op: s.op,
    text: s.op === "remove" ? b[s.b]! : a[s.a]!,
  }));
  const changed = lines.flatMap((l, i) => (l.op === "keep" ? [] : [i]));
  if (changed.length === 0) return [];
  const near = (i: number) => changed.some((c) => Math.abs(c - i) <= context);
  const out: WordsLine[] = [];
  lines.forEach((line, i) => {
    if (line.op !== "keep" || near(i)) return void out.push(line);
    const last = out[out.length - 1];
    if (last?.op === "skip") last.count++;
    else out.push({ op: "skip", count: 1 });
  });
  return out;
}
