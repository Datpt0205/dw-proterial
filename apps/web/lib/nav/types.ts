import type { ComponentType } from "react";

/**
 * A nav icon: an `@ant-design/icons` component (the Sales nav, and every new
 * one) or a lucide icon the platform pages still use. The bar draws it at
 * 1rem with `className`, and hides it from assistive tech.
 */
export type NavIcon = ComponentType<{
  className?: string;
  "aria-hidden"?: boolean;
}>;

export interface NavItem {
  href: string;
  label: string;
  hint: string;
  icon: NavIcon;
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
  /** Administers the tenant or the platform (see `barNav`). */
  administration?: boolean;
}

/**
 * Pages that sit under one name in the navbar: a submenu on the bar, a section
 * in the drawer. A group has no page of its own and shows only while one of
 * its items does.
 */
export interface NavGroup {
  key: string;
  label: string;
  icon: NavIcon;
  items: NavItem[];
  /** Administers the tenant or the platform (see `barNav`). */
  administration?: boolean;
  /**
   * Set on a bounded context's group: the product it is, and the prefix its
   * role keys carry (the context's migration owns the keys). Someone whose
   * work is this context alone gets its pages as the bar (`barNav`) and their
   * role named by the role catalogue.
   */
  context?: { product: string; roleKeyPrefix: string };
}

export type NavEntry = NavItem | NavGroup;

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return "items" in entry;
}
