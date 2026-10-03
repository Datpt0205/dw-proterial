import type { LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  exact?: boolean;
  /** Scope required to see this item (omit = always visible). */
  scope?: string;
  /**
   * Roles this item is for; the user needs one of them (omit = every role).
   * This is navigation, not authorization — the API still checks `scope`.
   */
  roles?: string[];
  /** Key into `useNavBadges()` for a count shown beside the label. */
  badgeKey?: string;
  /** Shown only to a Platform Operator (ADR-002), regardless of scope/role. */
  operatorOnly?: boolean;
}

/**
 * Pages that sit under one name in the navbar: a submenu on the bar, a section
 * in the drawer. A group has no page of its own and shows only while one of
 * its items does.
 */
export interface NavGroup {
  key: string;
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

export type NavEntry = NavItem | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return "items" in entry;
}
