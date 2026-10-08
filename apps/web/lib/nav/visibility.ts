import { hasAnyRole } from "./roles";
import type { NavItem } from "./types";

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
