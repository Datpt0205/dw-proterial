import { z } from "zod";

/**
 * The page shape every list endpoint returns. Mirrors `dw_kernel.pagination`.
 *
 * `next_cursor` is an opaque string, never a number: the server encodes the
 * position of the last row it handed over, and nothing about that encoding is
 * part of the contract except that it round-trips. Do not parse it, compare it,
 * or try to build one — a cursor the client invented, or one carried over from
 * a listing with different filters, is refused with a 422 rather than silently
 * answered from the wrong window.
 *
 * `next_cursor === null` is the only stop condition. An empty `items` is not:
 * a filtered listing can return an empty page mid-run and still have rows
 * behind it.
 */
export const pageSchema = <ItemSchema extends z.ZodTypeAny>(item: ItemSchema) =>
  z.object({
    items: z.array(item),
    next_cursor: z.string().nullable(),
  });

/** One page of `Item`, as `pageSchema` parses it. */
export interface Page<Item> {
  items: Item[];
  next_cursor: string | null;
}

/** How a caller asks for a page: a size, and where the previous one ended. */
export interface PageParams {
  limit?: number;
  cursor?: string | null;
}

/**
 * Render `PageParams` as a query string fragment, cursor included only when
 * there is one — sending `cursor=null` would be a cursor, and an unreadable one.
 */
export function pageQueryString(params: PageParams = {}): string {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.cursor) search.set("cursor", params.cursor);
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}
