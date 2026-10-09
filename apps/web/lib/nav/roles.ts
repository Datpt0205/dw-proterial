/**
 * Role keys the workbench branches on.
 *
 * A role decides what a user is shown; a scope decides what they may do, and the
 * API checks the scope on every request regardless of what the shell rendered.
 * Hiding a link is therefore navigation, never authorization.
 */

/**
 * How a role key reads to a person: the ONE label table for roles in the web
 * app (session menu, members, hierarchy, dev login, role catalog). The tenant
 * role catalog in the database owns the keys; this owns only the wording, and
 * `__tests__/roles.test.ts` fails when the catalog seeds a key this table does
 * not name.
 *
 * PLUG-IN POINT: a bounded context adds its own roles' labels here, in the same
 * change that seeds them.
 */
const ROLE_LABELS: Record<string, string> = {
  member: "Nhân viên",
  approver: "Người duyệt",
  manager: "Quản lý",
  director: "Giám đốc",
  executive: "Ban điều hành",
  // Naming (2026-09-10): org_admin manages users, roles and settings;
  // platform_admin is the in-tenant role that passes every scope. Neither is
  // the cross-tenant operator who creates tenants (OPERATOR_LABEL).
  org_admin: "Quản trị hệ thống",
  platform_admin: "Quản trị toàn quyền",
  // Sales (dw_sales), seeded by its own migration (68305ebe4a83) with these
  // same names in the role catalog.
  sales_pic: "Sales phụ trách (PIC)",
  sales_head: "Trưởng bộ phận Sales",
  sales_viewer: "Lãnh đạo (xem tổng hợp)",
};

/** How a platform operator (creates tenants, ADR-002) is named; not a role key. */
export const OPERATOR_LABEL = "Quản trị nền tảng";

/** What a role with no label and no catalog name reads as: never its code. */
export const UNNAMED_ROLE = "Vai khác";

/**
 * Label for a single role key. A key this table does not name falls back to
 * the name the role catalog gave it, then to a generic label: a raw key like
 * `sc_operator` is never shown to a person.
 */
export function roleLabel(key: string, catalogName?: string): string {
  return ROLE_LABELS[key] ?? catalogName ?? UNNAMED_ROLE;
}

/** Deduplicated, comma-joined labels for a member's role keys. */
export function roleLabels(keys: readonly string[]): string {
  return [...new Set(keys.map((key) => roleLabel(key)))].join(", ");
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
// adds is unranked.
const ROLE_RANK = ["member", "approver", "org_admin", "platform_admin"];

/**
 * What the account menu calls the person. In a bounded context's bar, the
 * roles that context gave them (`roleKeyPrefix`); elsewhere, the most senior
 * platform role, a Platform Operator first. Every name comes from
 * `roleLabel`: this table, then the role catalogue's name
 * (`/auth/bootstrap` `role_names`) for a key the table does not hold, never
 * the key.
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
  const named = (key: string) => roleLabel(key, roleNames[key]);
  if (contextPrefix) {
    const own = roles.filter((key) => key.startsWith(contextPrefix));
    if (own.length) return [...new Set(own.map(named))].join(", ");
  }
  if (isPlatformOperator) return OPERATOR_LABEL;
  const top = [...roles].sort(
    (a, b) => ROLE_RANK.indexOf(b) - ROLE_RANK.indexOf(a),
  )[0];
  if (!top) return null;
  return named(top);
}
