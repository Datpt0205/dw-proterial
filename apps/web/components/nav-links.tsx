"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";
import { useNavBadges } from "../lib/nav/badges";
import { NAV_ITEMS } from "../lib/nav/registry";
import { hasAnyRole } from "../lib/nav/roles";

export function NavLinks({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  const { hasScope, roles, isPlatformOperator } = useAuth();
  const badges = useNavBadges();
  // Three filters: scope is the permission the API enforces anyway, role is who
  // the page is for, and operatorOnly is the cross-tenant provisioning area.
  const visible = NAV_ITEMS.filter(
    (item) =>
      (!item.operatorOnly || isPlatformOperator) &&
      (!item.scope || hasScope(item.scope)) &&
      (!item.roles || hasAnyRole(roles, item.roles)),
  );
  return (
    <nav
      aria-label="Main navigation"
      className={
        mobile ? "flex min-w-max items-center gap-1" : "flex flex-col gap-0.5"
      }
    >
      {visible.map((item) => {
        const active = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(item.href + "/");
        const Icon = item.icon;
        return (
          <div key={item.href}>
            <Link
              href={item.href}
              title={item.hint}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-all duration-200",
                active
                  ? "bg-primary font-semibold text-white shadow-[0_8px_22px_rgba(11,49,85,.18)]"
                  : "font-medium text-slate-600 hover:translate-x-0.5 hover:bg-sidebar-accent hover:text-foreground",
              )}
            >
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-md transition-colors",
                  active
                    ? "bg-white/12"
                    : "bg-slate-100 text-slate-500 group-hover:bg-white group-hover:text-primary",
                )}
              >
                <Icon className="size-3.5" />
              </span>
              <span className="flex-1 truncate">{item.label}</span>
              {item.badgeKey && badges[item.badgeKey] ? (
                <span
                  className={cn(
                    "rounded-full px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
                    active
                      ? "bg-white/20 text-white"
                      : "bg-muted text-muted-foreground",
                  )}
                >
                  {badges[item.badgeKey]}
                </span>
              ) : null}
              {active && (
                <span className="absolute -left-1 h-5 w-1 rounded-full bg-sky-300" />
              )}
            </Link>
          </div>
        );
      })}
    </nav>
  );
}
