"use client";

import { useCallback } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";
import { SALES_BADGE } from "./badge-keys";

/**
 * The Sales counts beside the nav items: the viewer's waiting work and the
 * messages DW1 has not processed. Read again on every page change, so a
 * count does not outlive the action that changed it by more than one
 * navigation. A failed read shows no count: a badge is decoration and never
 * takes the nav down. Asked only of someone who may read Sales cases.
 */
export function useSalesNavBadges(): Record<string, number> {
  const { hasScope } = useAuth();
  const pathname = usePathname();
  const enabled = hasScope("sales.case.read");
  const work = useResource(
    `nav/sales/my-work@${pathname}`,
    useCallback(async () => salesApi().myWork(), []),
    { enabled },
  );
  const inbox = useResource(
    `nav/sales/inbox@${pathname}`,
    useCallback(async () => salesApi().inbox(), []),
    { enabled },
  );
  const counts: Record<string, number> = {};
  if (work.data) counts[SALES_BADGE.myWork] = work.data.length;
  if (inbox.data)
    counts[SALES_BADGE.inbox] = inbox.data.filter(
      (m) => m.disposition.kind === "not_yet_processed",
    ).length;
  return counts;
}
