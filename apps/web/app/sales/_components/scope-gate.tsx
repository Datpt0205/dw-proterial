"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Forbidden } from "../../../components/region-state";
import { useAuth } from "../../../lib/auth/auth-context";
import { SCOPE } from "./sales-frame";

/**
 * A Sales page the viewer's scopes do not reach draws the 403 state, without
 * asking the server first (the server refuses it anyway). A viewer who reads
 * the overview is pointed there.
 */
export function ScopeGate({
  scope,
  children,
}: {
  scope: string;
  children: ReactNode;
}) {
  const { hasScope } = useAuth();
  if (hasScope(scope)) return <>{children}</>;
  return (
    <Forbidden
      extra={
        hasScope(SCOPE.overview) ? (
          <Link href="/sales/overview">Mở Tổng quan quy trình</Link>
        ) : null
      }
    />
  );
}
