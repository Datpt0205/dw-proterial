"use client";

import { useCallback, useMemo } from "react";
import { salesApi } from "./api";
import { useResource } from "./use-resource";

/**
 * The cases whose conversation holds an answer the person has not seen
 * (ticket 46): one read for a whole list, never one per row. A list marks
 * the rows it already holds; a failed read marks none, which loses a hint
 * and nothing else.
 */
export function useUnreadCases(): ReadonlySet<string> {
  const unread = useResource(
    "assistant-unread",
    useCallback(() => salesApi().assistantUnread(), []),
  );
  return useMemo(() => new Set(unread.data ?? []), [unread.data]);
}
