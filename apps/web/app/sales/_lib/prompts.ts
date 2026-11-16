import type { SalesSchemas } from "@dw/api-client";

export type PromptsView = SalesSchemas["PromptsView"];
export type PromptVersion = SalesSchemas["PromptVersionView"];
export type Demonstration = SalesSchemas["Demonstration"];
export type PromptReplay = SalesSchemas["PromptReplay"];

/** One decided line's identity: its words, as a reading sees them, and the kept code. */
function lineKey(d: Demonstration): string {
  return `${d.description.trim().toLowerCase()}\u0000${d.prv_code}`;
}

export interface DemonstrationChanges {
  added: Demonstration[];
  removed: Demonstration[];
  kept: Demonstration[];
}

/**
 * What a version changes in the words every reading is shown, against the
 * version in force: the decided lines it adds, the ones it drops and the
 * ones both show. The instructions are the platform's prompt in both, so
 * these lines are the whole difference (ticket 43).
 */
export function demonstrationChanges(
  inForce: readonly Demonstration[],
  proposed: readonly Demonstration[],
): DemonstrationChanges {
  const before = new Set(inForce.map(lineKey));
  const after = new Set(proposed.map(lineKey));
  return {
    added: proposed.filter((d) => !before.has(lineKey(d))),
    removed: inForce.filter((d) => !after.has(lineKey(d))),
    kept: proposed.filter((d) => before.has(lineKey(d))),
  };
}

/** The replay in one line: "Đọc đúng 19/20 dòng đã quyết (bản đang dùng: 0/20)". */
export function scoreLine(replay: PromptReplay): string {
  const n = replay.cases;
  return `Đọc đúng ${replay.right_after}/${n} dòng đã quyết (bản đang dùng: ${replay.right_before}/${n})`;
}

/**
 * The security cases, said plainly. The lane proposes nothing that fails
 * one, so a stored replay always passed every case it names.
 */
export function securityLine(replay: PromptReplay): string {
  return `Qua cả ${replay.security_cases} ca bảo mật`;
}
