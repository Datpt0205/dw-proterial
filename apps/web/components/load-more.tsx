"use client";

import { Button } from "@dw/ui";

interface LoadMoreProps {
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  /** How many rows are on screen, so the footer can say where the list stands. */
  shown: number;
  /** Plural noun for those rows: "events", "documents", "approvals". */
  noun: string;
  /**
   * Set when the screen filters the loaded rows in the browser. The filter then
   * only sees what has been fetched, and a user who searches a list with more
   * behind it has to be told that — otherwise an empty result reads as "there is
   * none" when it means "there is none so far".
   */
  filtered?: boolean;
}

/**
 * The end of a cursor-paged list: what is shown, and whether there is more.
 *
 * Rendered even when the list is complete. A footer that appears only when
 * there is a next page leaves the user unable to tell a finished list from one
 * whose button they have not scrolled to yet — which is the same ambiguity the
 * old `limit: 200` had, just further down the page.
 */
export function LoadMore({
  hasMore,
  loading,
  onLoadMore,
  shown,
  noun,
  filtered = false,
}: LoadMoreProps) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
      <span>
        {hasMore ? `${shown} ${noun} so far` : `${shown} ${noun}`}
        {hasMore && filtered && " — the search covers these only"}
      </span>
      {hasMore && (
        <Button variant="outline" onClick={onLoadMore} disabled={loading}>
          {loading ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}
