"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { RegionState, type PageHeaderCrumb } from "@dw/ui";
import { useAuth } from "../../../lib/auth/auth-context";

/**
 * A DW2 page the viewer's scopes do not reach draws the 403 state without
 * asking the server first; the server refuses it anyway. Any one of `scope`
 * opens the page, for a page the API opens to either.
 */
export function ScopeGate({
  scope,
  children,
}: {
  scope: readonly string[];
  children: ReactNode;
}) {
  const { hasScope } = useAuth();
  if (scope.some((s) => hasScope(s))) return <>{children}</>;
  return (
    <RegionState
      kind="forbidden"
      description="Vai của bạn trong không gian làm việc này không gồm trang này. Nếu bạn cần, nhờ quản trị hệ thống cấp quyền."
      action={<Link href="/">Về trang chính</Link>}
    />
  );
}

/** A DW2 page's breadcrumb: "Mua hàng", then each level down to the page. */
export function purchasingCrumbs(
  ...levels: (string | { title: string; href: string })[]
): PageHeaderCrumb[] {
  return [
    { title: <Link href="/purchasing">Mua hàng</Link> },
    ...levels.map((level) =>
      typeof level === "string"
        ? { title: level }
        : { title: <Link href={level.href}>{level.title}</Link> },
    ),
  ];
}
