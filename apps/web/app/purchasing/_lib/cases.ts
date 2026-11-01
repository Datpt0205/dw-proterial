"use client";

import type { Page, PurchaseCase } from "@dw/api-client";
import { purchasingApi } from "./api";

/**
 * One page of cases in the shape `useCachedPages` reads: the API pages by a
 * keyset (`before_at`, `before_id`), carried here as one opaque cursor.
 */
export async function casePage(
  cursor: string | null,
): Promise<Page<PurchaseCase>> {
  const [at, id] = cursor ? cursor.split("|") : [];
  const page = await purchasingApi().cases(at && id ? { at, id } : null);
  return {
    items: page.items,
    next_cursor:
      page.next_before_at && page.next_before_id
        ? `${page.next_before_at}|${page.next_before_id}`
        : null,
  };
}
