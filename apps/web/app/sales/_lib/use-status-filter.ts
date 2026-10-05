"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * A list's view, kept in the URL (`?tab=…&q=…&sort=…&status=a,b`), so the
 * view is a link a colleague can open and Back restores (ui-quality §11).
 * A value equal to its default is left out of the URL.
 */
function useParam(
  name: string,
): [string | null, (next: string | null) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = params.get(name);
  const set = useCallback(
    (next: string | null) => {
      const query = new URLSearchParams(params.toString());
      if (next) query.set(name, next);
      else query.delete(name);
      router.replace(`${pathname}${query.size ? `?${query}` : ""}`, {
        scroll: false,
      });
    },
    [params, router, pathname, name],
  );
  return [value, set];
}

/** The status filter (`?status=a,b`). */
export function useStatusFilter() {
  const [raw, setRaw] = useParam("status");
  const selected = useMemo(() => (raw ?? "").split(",").filter(Boolean), [raw]);
  const set = useCallback(
    (next: string[]) => setRaw(next.length ? next.join(",") : null),
    [setRaw],
  );
  return [selected, set] as const;
}

/** The tab, the search text and the sort of a list, each with its default. */
export function useListView<Tab extends string, Sort extends string>(
  tabs: readonly Tab[],
  defaultTab: Tab,
  sorts: readonly Sort[],
  defaultSort: Sort,
) {
  const [rawTab, setRawTab] = useParam("tab");
  const [rawSort, setRawSort] = useParam("sort");
  const [rawQuery, setRawQuery] = useParam("q");
  const tab = tabs.find((t) => t === rawTab) ?? defaultTab;
  const sort = sorts.find((s) => s === rawSort) ?? defaultSort;
  return {
    tab,
    setTab: (next: Tab) => setRawTab(next === defaultTab ? null : next),
    sort,
    setSort: (next: Sort) => setRawSort(next === defaultSort ? null : next),
    query: rawQuery ?? "",
    setQuery: (next: string) => setRawQuery(next || null),
  };
}
