"use client";

import { RegionState } from "@dw/ui";
import type { ReactNode } from "react";
import Link from "next/link";
import { useAuth } from "../../../lib/auth/auth-context";
import { SCOPE } from "./sales-frame";

/**
 * A Sales page the viewer's scopes do not reach draws the 403 state, without
 * asking the server first (the server refuses it anyway). A viewer who reads
 * the overview is pointed there. `scope` may list several: any one opens the
 * page, for a page the API opens to either.
 */
export function ScopeGate({
  scope,
  children,
}: {
  scope: string | readonly string[];
  children: ReactNode;
}) {
  const { hasScope } = useAuth();
  const any = typeof scope === "string" ? [scope] : scope;
  if (any.some((s) => hasScope(s))) return <>{children}</>;
  return (
    <RegionState
      kind="forbidden"
      description="Vai của bạn trong không gian làm việc này không gồm trang này. Nếu bạn cần, nhờ quản trị hệ thống cấp quyền."
      action={
        hasScope(SCOPE.overview) ? (
          <Link href="/sales/overview">Mở Tổng quan quy trình</Link>
        ) : (
          <Link href="/">Về trang chính</Link>
        )
      }
    />
  );
}
