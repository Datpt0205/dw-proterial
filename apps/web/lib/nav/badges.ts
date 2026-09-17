"use client";

/**
 * Counts the sidebar shows next to a nav item.
 *
 * A nav manifest declares `badgeKey`; this resolves the number. Keeping the
 * fetch here rather than in the manifest keeps the manifest declarative and
 * server-safe, and keeps one place to add the next counter.
 *
 * PLUG-IN POINT: a bounded context that wants a count fetches it here, guarded
 * by the scope the count needs and swallowing a failed read — a badge is
 * decoration and must never take the nav down. The platform shell counts
 * nothing of its own, so this starts empty.
 */
export function useNavBadges(): Record<string, number> {
  return {};
}
