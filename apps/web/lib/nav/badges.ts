"use client";

import { useSalesNavBadges } from "../../app/sales/_meta/badges";

/**
 * Counts the navbar shows next to a nav item.
 *
 * A nav manifest declares `badgeKey`; this resolves the number. Keeping the
 * fetch out of the manifest keeps the manifest declarative and server-safe,
 * and keeps one place to add the next counter.
 *
 * PLUG-IN POINT: a bounded context that wants a count ships a hook beside its
 * nav manifest, guarded by the scope the count needs and swallowing a failed
 * read (a badge is decoration and must never take the nav down), and adds it
 * here once. The platform shell counts nothing of its own.
 */
export function useNavBadges(): Record<string, number> {
  return { ...useSalesNavBadges() };
}
