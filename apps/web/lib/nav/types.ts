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
