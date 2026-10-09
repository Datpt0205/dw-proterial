import { hasAnyRole } from "./roles";
import {
  isNavGroup,
  type NavEntry,
  type NavGroup,
  type NavItem,
} from "./types";

/** What the menu knows about the person looking at it. */
export interface NavViewer {
  isPlatformOperator: boolean;
  hasScope: (scope: string) => boolean;
  roles: readonly string[];
}

/**
 * Whether a nav item is offered to this viewer: the ONE rule, read by the menu
 * (`components/app-frame.tsx`) and the home page's shortcuts alike, so the
 * home page never invites someone to an item the menu hides.
 *
 * Navigation, not authorization: the API checks the scope on every request.
 */
export function isNavItemVisible(item: NavItem, viewer: NavViewer): boolean {
  if (item.operatorOnly && !viewer.isPlatformOperator) return false;
  if (item.scope && !viewer.hasScope(item.scope)) return false;
  if (item.anyScope !== undefined) {
    // An empty list asks for nothing and would show to everyone: refuse it.
    if (item.anyScope.length === 0) return false;
    if (!item.anyScope.some((scope) => viewer.hasScope(scope))) return false;
  }
  if (item.roles && !hasAnyRole(viewer.roles, item.roles)) return false;
  return true;
}

/** The entries the person is shown; a group keeps only the items they see. */
export function visibleNav(
  entries: readonly NavEntry[],
  viewer: NavViewer,
): NavEntry[] {
  return entries.flatMap((entry): NavEntry[] => {
    if (!isNavGroup(entry))
      return isNavItemVisible(entry, viewer) ? [entry] : [];
    const items = entry.items.filter((item) => isNavItemVisible(item, viewer));
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
