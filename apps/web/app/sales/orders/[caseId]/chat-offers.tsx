"use client";

import { useMemo, type ReactNode } from "react";
import type { ReplyKind, SalesSchemas } from "@dw/api-client";
import type { CaseOffers } from "../../_components/case-chat";
import { CustomerReminder } from "../../_components/customer-reminder";
import { ThreadSummary } from "../../_components/thread-summary";
import { AgentReply, AGENT_KINDS } from "./agent-reply";

type Order = SalesSchemas["OrderCaseView"];

/** "Bản AI soạn" beside a template draft the model may word (ticket 32),
 * or null: one answer for the files panel and the case's conversation. */
export function agentDraft(caseId: string, kind: string): ReactNode {
  return AGENT_KINDS.has(kind) ? (
    <AgentReply key={kind} caseId={caseId} kind={kind as ReplyKind} />
  ) : null;
}

/** The order waits on the customer's corrected PO: a reminder may be drafted. */
export function waitsOnCustomer(status: Order["status"]): boolean {
  return status === "correction_requested";
}

/**
 * The order's own controls for a step asked in its conversation (ticket 46),
 * under the same conditions the case page draws them with: one owner for the
 * case page and the item in "Việc của tôi" (ticket 79). Nothing while the
 * order is still loading (`status` undefined).
 */
export function useOrderChatOffers(
  caseId: string,
  status: Order["status"] | undefined,
  available: readonly string[] | undefined,
): CaseOffers {
  return useMemo<CaseOffers>(() => {
    if (status === undefined) return {};
    const drafts = (available ?? [])
      .map((k) => agentDraft(caseId, k))
      .filter((node) => node !== null);
    return {
      thread_summary: <ThreadSummary kind="order" caseId={caseId} />,
      ...(waitsOnCustomer(status)
        ? {
            customer_reminder: (
              <CustomerReminder kind="order" caseId={caseId} />
            ),
          }
        : {}),
      ...(drafts.length ? { reply_draft: <>{drafts}</> } : {}),
    };
  }, [caseId, status, available]);
}
