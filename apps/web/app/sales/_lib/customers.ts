"use client";

import { useCallback, useMemo } from "react";
import { salesApi } from "./api";
import { useResource } from "./use-resource";

/**
 * A customer's name for its code, from the (mock) customer master data, the
 * owner of names. A code the master data does not hold reads as nothing, and
 * the screen shows the code alone.
 */
export function useCustomerName(): (code: string | null | undefined) => string {
  const customers = useResource(
    "sales/master-data/customers",
    useCallback(() => salesApi().customers(), []),
  );
  const byCode = useMemo(
    () => new Map((customers.data?.items ?? []).map((c) => [c.code, c.name])),
    [customers.data],
  );
  return useCallback(
    (code) => (code ? (byCode.get(code) ?? "") : ""),
    [byCode],
  );
}
