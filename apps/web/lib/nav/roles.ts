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
