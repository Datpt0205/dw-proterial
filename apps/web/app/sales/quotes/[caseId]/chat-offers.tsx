"use client";

import { useMemo } from "react";
import type { CaseOffers } from "../../_components/case-chat";
import { CustomerReminder } from "../../_components/customer-reminder";
import { ThreadSummary } from "../../_components/thread-summary";

/** The quote waits on the customer's answer about the spec: a reminder
 * may be drafted. */
export function waitsOnCustomer(status: string): boolean {
  return status === "spec_discussion";
}

/**
 * The quotation's own controls for a step asked in its conversation (ticket
 * 46), under the same conditions the case page draws them with: one owner for
 * the case page and the item in "Việc của tôi" (ticket 79). A quote has no
 * model-worded mail to the customer: none is offered. Nothing while the quote
 * is still loading (`status` undefined).
 */
export function useQuoteChatOffers(
  caseId: string,
  status: string | undefined,
): CaseOffers {
  return useMemo<CaseOffers>(() => {
    if (status === undefined) return {};
    return {
      thread_summary: <ThreadSummary kind="quote" caseId={caseId} />,
      ...(waitsOnCustomer(status)
        ? {
            customer_reminder: (
              <CustomerReminder kind="quote" caseId={caseId} />
            ),
          }
        : {}),
    };
  }, [caseId, status]);
}
