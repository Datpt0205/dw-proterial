import type { DocPath } from "./rule-schema";

/**
 * What a proposed version changes against the version in force, field by
 * field (ticket 40): read by the person proposing it before it is sent, and
 * by the head deciding it on `/approvals`.
 *
 * Objects and maps are compared key by key. A list is aligned by its items'
 * contents (a longest common subsequence), so an inserted row reads as one
 * added row and not as every row after it changed; a removed and an added
 * item at the same place are paired and compared field by field.
 */
export type Change =
  | { kind: "changed"; path: DocPath; before: unknown; after: unknown }
  | { kind: "added"; path: DocPath; after: unknown }
  | { kind: "removed"; path: DocPath; before: unknown };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Equality of JSON values; a decimal "0.10" equals 0.1. */
export function same(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) && Array.isArray(b))
    return a.length === b.length && a.every((v, i) => same(v, b[i]));
  if (isRecord(a) && isRecord(b)) {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    return [...keys].every((k) => same(a[k], b[k]));
  }
  if (numeric(a) && numeric(b)) return Number(a) === Number(b);
  return a === b;
}

function numeric(value: unknown): boolean {
  return (
    (typeof value === "number" && Number.isFinite(value)) ||
    (typeof value === "string" && /^[+-]?\d+(\.\d+)?$/.test(value))
  );
}

export function diffDocuments(before: unknown, after: unknown): Change[] {
  const out: Change[] = [];
  walk(before, after, [], out);
  return out;
}

function walk(before: unknown, after: unknown, path: DocPath, out: Change[]) {
  if (same(before, after)) return;
  if (isRecord(before) && isRecord(after)) {
    const keys = [
      ...Object.keys(before),
      ...Object.keys(after).filter((k) => !(k in before)),
    ];
    for (const key of keys) {
      if (!(key in after))
        out.push({
          kind: "removed",
          path: [...path, key],
          before: before[key],
        });
      else if (!(key in before))
        out.push({ kind: "added", path: [...path, key], after: after[key] });
      else walk(before[key], after[key], [...path, key], out);
    }
    return;
  }
  if (Array.isArray(before) && Array.isArray(after)) {
    listDiff(before, after, path, out);
    return;
  }
  out.push({ kind: "changed", path, before, after });
}

type Step =
  | { op: "keep"; b: number; a: number }
  | { op: "remove"; b: number }
  | { op: "add"; a: number };

function align(before: unknown[], after: unknown[]): Step[] {
  const n = before.length;
  const m = after.length;
  const lcs: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i]![j] = same(before[i], after[j])
        ? lcs[i + 1]![j + 1]! + 1
        : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
  const steps: Step[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (same(before[i], after[j])) steps.push({ op: "keep", b: i++, a: j++ });
    else if (lcs[i + 1]![j]! >= lcs[i]![j + 1]!)
      steps.push({ op: "remove", b: i++ });
    else steps.push({ op: "add", a: j++ });
  }
  while (i < n) steps.push({ op: "remove", b: i++ });
  while (j < m) steps.push({ op: "add", a: j++ });
  return steps;
}

function listDiff(
  before: unknown[],
  after: unknown[],
  path: DocPath,
  out: Change[],
) {
  const steps = align(before, after);
  let k = 0;
  while (k < steps.length) {
    if (steps[k]!.op === "keep") {
      k++;
      continue;
    }
    // A run of removals and additions between two kept items.
    const removed: number[] = [];
    const added: number[] = [];
    while (k < steps.length && steps[k]!.op !== "keep") {
      const s = steps[k++]!;
      if (s.op === "remove") removed.push(s.b);
      if (s.op === "add") added.push(s.a);
    }
    const paired = Math.min(removed.length, added.length);
    for (let p = 0; p < paired; p++) {
      const b = before[removed[p]!];
      const a = after[added[p]!];
      // Two objects in one place are one item edited; two scalars are a swap.
      if (isRecord(b) && isRecord(a)) walk(b, a, [...path, added[p]!], out);
      else
        out.push({
          kind: "changed",
          path: [...path, added[p]!],
          before: b,
          after: a,
        });
    }
    for (const b of removed.slice(paired))
      out.push({ kind: "removed", path: [...path, b], before: before[b] });
    for (const a of added.slice(paired))
      out.push({ kind: "added", path: [...path, a], after: after[a] });
  }
}
