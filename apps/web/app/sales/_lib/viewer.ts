"use client";

import { useMemo } from "react";
import { useAuth } from "../../../lib/auth/auth-context";
import type { Viewer } from "./order-actions";

/**
 * The signed-in person as the Sales screens test them. The session's scopes
 * are the membership's effective ones (`/auth/bootstrap` unions the role's
 * and the permission sets', as the access context does), so An's NOC/ESF
 * acknowledgement and Khoa's deputy approval show as offered. The server
 * decides either way.
 */
export function useSalesViewer(): Viewer {
  const { principalId, hasScope } = useAuth();
  return useMemo(() => ({ principalId, hasScope }), [principalId, hasScope]);
}
