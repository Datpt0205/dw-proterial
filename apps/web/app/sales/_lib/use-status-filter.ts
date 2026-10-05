"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * A list's status filter, kept in the URL (`?status=a,b`) so the filtered
 * view is a link a colleague can open and Back restores (ui-quality §11).
 */
export function useStatusFilter() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selected = useMemo(
    () => (params.get("status") ?? "").split(",").filter(Boolean),
    [params],
  );
  const set = useCallback(
    (next: string[]) => {
      const query = new URLSearchParams(params.toString());
      if (next.length) query.set("status", next.join(","));
      else query.delete("status");
      router.replace(`${pathname}${query.size ? `?${query}` : ""}`, {
        scroll: false,
      });
    },
    [params, router, pathname],
  );
  return [selected, set] as const;
}
