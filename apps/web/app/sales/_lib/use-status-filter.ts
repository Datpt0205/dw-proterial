"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ACTIVITY_PARAMS, activityFromUrl } from "./activity";

/**
 * A list's view, kept in the URL (`?tab=…&q=…&sort=…&status=a,b`), so the
 * view is a link a colleague can open and Back restores (ui-quality §11).
 * A value equal to its default is left out of the URL.
 */
export function useUrlParam(
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
  const [raw, setRaw] = useUrlParam("status");
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
  const [rawTab, setRawTab] = useUrlParam("tab");
  const [rawSort, setRawSort] = useUrlParam("sort");
  const [rawQuery, setRawQuery] = useUrlParam("q");
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

/**
 * The activity filter a count on "Hoạt động DW1" put in the URL (`?step=…&
 * from=…&to=…`), as the list's API call takes it, and a way to drop it. Null
 * when the URL carries none.
 */
export function useActivityFilter() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filter = useMemo(
    () => activityFromUrl(new URLSearchParams(params.toString())),
    [params],
  );
  const clear = useCallback(() => {
    const query = new URLSearchParams(params.toString());
    for (const name of ACTIVITY_PARAMS) query.delete(name);
    router.replace(`${pathname}${query.size ? `?${query}` : ""}`, {
      scroll: false,
    });
  }, [params, router, pathname]);
  return [filter, clear] as const;
}
