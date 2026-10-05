/**
 * Role keys the workbench branches on.
 *
 * A role decides what a user is shown; a scope decides what they may do, and the
 * API checks the scope on every request regardless of what the shell rendered.
 * Hiding a link is therefore navigation, never authorization.
 */

/**
 * Friendly English labels shown in place of raw role keys. The tenant role
 * catalog in the database owns the keys themselves; this owns only the wording.
 * An unknown key falls back to the key, so a role a bounded context adds still
 * reads as something rather than disappearing.
 */
const ROLE_LABELS: Record<string, string> = {
  member: "Staff",
  approver: "Manager",
  // Naming (2026-09-10): the in-tenant god-mode role reads as "Tenant Admin";
  // "Platform Admin" is reserved for the cross-tenant operator that creates
  // tenants (see SessionChip). org_admin manages users/roles/settings, shown
  // as "System Admin".
  org_admin: "System Admin",
  platform_admin: "Tenant Admin",
};

/** Label for a single role key; unknown keys fall back to the raw key. */
export function roleLabel(key: string): string {
  return ROLE_LABELS[key] ?? key;
}

/** Deduplicated, comma-joined labels for a member's role keys. */
export function roleLabels(keys: readonly string[]): string {
  return [...new Set(keys.map(roleLabel))].join(", ");
}

/** True when the user holds at least one of the roles an item asks for. */
export function hasAnyRole(
  userRoles: readonly string[],
  required: readonly string[],
): boolean {
  const held = new Set(userRoles);
  return required.some((role) => held.has(role));
}

// Seniority low → high among the platform's roles. A role a bounded context
// adds is unranked and is named by the role catalogue instead.
const ROLE_RANK = ["member", "approver", "org_admin", "platform_admin"];

/**
 * What the account menu calls the person. In a bounded context's bar, the
 * roles that context gave them (`roleKeyPrefix`), by the names the role
 * catalogue gives them (`/auth/bootstrap` `role_names`, Vietnamese for Sales):
 * the screen keeps no copy of those names. Elsewhere, the most senior platform
 * role in the wording above, a Platform Operator first; an unranked role the
 * person holds alone reads as its catalogue name.
 */
export function displayRole({
  roles,
  roleNames,
  contextPrefix,
  isPlatformOperator,
}: {
  roles: readonly string[];
  roleNames: Readonly<Record<string, string>>;
  contextPrefix: string | null;
  isPlatformOperator: boolean;
}): string | null {
  const named = (key: string) => roleNames[key] ?? ROLE_LABELS[key] ?? key;
  if (contextPrefix) {
    const own = roles.filter((key) => key.startsWith(contextPrefix));
    if (own.length) return own.map(named).join(", ");
  }
  if (isPlatformOperator) return "Platform Admin";
  const top = [...roles].sort(
    (a, b) => ROLE_RANK.indexOf(b) - ROLE_RANK.indexOf(a),
  )[0];
  if (!top) return null;
  return ROLE_LABELS[top] ?? named(top);
}
