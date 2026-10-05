import { hasAnyRole } from "./roles";
import {
  isNavGroup,
  type NavEntry,
  type NavGroup,
  type NavItem,
} from "./types";

/** What the nav filter reads from the signed-in person; `useAuth()` is one. */
export interface NavViewer {
  isPlatformOperator: boolean;
  hasScope: (scope: string) => boolean;
  roles: readonly string[];
}

/**
 * Whether the person is shown this page. Three filters: scope is the
 * permission the API enforces anyway, role is who the page is for, and
 * operatorOnly is the cross-tenant provisioning area. Navigation, never
 * authorization: the API checks the scope on every request.
 */
export function canSee(item: NavItem, viewer: NavViewer): boolean {
  return (
    (!item.operatorOnly || viewer.isPlatformOperator) &&
    (!item.scope || viewer.hasScope(item.scope)) &&
    (!item.roles || hasAnyRole(viewer.roles, item.roles))
  );
}

/** The entries the person is shown; a group keeps only the items they see. */
export function visibleNav(
  entries: readonly NavEntry[],
  viewer: NavViewer,
): NavEntry[] {
  return entries.flatMap((entry): NavEntry[] => {
    if (!isNavGroup(entry)) return canSee(entry, viewer) ? [entry] : [];
    const items = entry.items.filter((item) => canSee(item, viewer));
    return items.length > 0 ? [{ ...entry, items }] : [];
  });
}

/** Every page in `entries`, groups opened up, in order. */
export function navPages(entries: readonly NavEntry[]): NavItem[] {
  return entries.flatMap((entry) => (isNavGroup(entry) ? entry.items : entry));
}

/**
 * The page the path is on: the longest href that matches it, where an `exact`
 * item matches only itself (so `/sales/orders` is "Đơn hàng", not the
 * overview at `/sales`).
 */
export function currentPage(
  pages: readonly NavItem[],
  pathname: string,
): NavItem | undefined {
  let best: NavItem | undefined;
  for (const page of pages) {
    const matches = page.exact
      ? pathname === page.href
      : pathname === page.href || pathname.startsWith(page.href + "/");
    if (matches && (!best || page.href.length > best.href.length)) best = page;
  }
  return best;
}

/** What the navbar draws: the entries, and the context they belong to. */
export interface Bar {
  entries: NavEntry[];
  /** The bounded context the bar is, when it is one. */
  context: NavGroup | null;
}

/**
 * The bar for what a person can see (`visibleNav`'s output). Someone who
 * reaches exactly one bounded context and administers nothing works in that
 * context: its pages are the bar and the platform's own pages (an
 * operational person never uses them) are left off. Anyone who administers
 * the tenant or the platform keeps every entry. Navigation, never
 * authorization: a page left off still answers its URL with the server's
 * decision.
 */
export function barNav(visible: readonly NavEntry[]): Bar {
  const contexts = visible.filter(
    (entry): entry is NavGroup => isNavGroup(entry) && !!entry.context,
  );
  const administers = visible.some((entry) => entry.administration);
  if (contexts.length === 1 && !administers)
    return { entries: contexts[0]!.items, context: contexts[0]! };
  return { entries: [...visible], context: null };
}
