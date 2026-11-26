import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

/**
 * Which of a case's own controls its conversation is offered (ticket 46),
 * read by the case page and by the item in "Việc của tôi" alike (ticket 79):
 * the conditions themselves, so a change to one fails here and not only on
 * a page that happens to be in that state.
 */

vi.mock("../api", () => ({ salesApi: () => ({}) }));

import { useOrderChatOffers } from "../../orders/[caseId]/chat-offers";
import { useQuoteChatOffers } from "../../quotes/[caseId]/chat-offers";

const CASE = "ca5e0000-0000-4000-8000-000000000001";

function orderOffers(status: string | undefined, available?: string[]) {
  return renderHook(() =>
    useOrderChatOffers(
      CASE,
      status as Parameters<typeof useOrderChatOffers>[1],
      available,
    ),
  ).result.current;
}

describe("An order's conversation is offered", () => {
  it("nothing while the order is still loading", () => {
    expect(orderOffers(undefined, ["confirmation_draft"])).toEqual({});
  });

  it("a reminder to the customer only while their corrected PO is awaited", () => {
    expect(orderOffers("correction_requested").customer_reminder).toBeTruthy();
    expect(orderOffers("in_review").customer_reminder).toBeUndefined();
    expect(orderOffers("confirmation_sent").customer_reminder).toBeUndefined();
  });

  it("a model-worded reply only for a draft the model may word", () => {
    expect(
      orderOffers("in_review", ["confirmation_draft"]).reply_draft,
    ).toBeTruthy();
    expect(
      orderOffers("in_review", ["bravo_upload_xlsx"]).reply_draft,
    ).toBeUndefined();
    expect(orderOffers("in_review").reply_draft).toBeUndefined();
  });

  it("the thread's summary at every step", () => {
    expect(orderOffers("in_review").thread_summary).toBeTruthy();
  });
});

describe("A quotation's conversation is offered", () => {
  it("nothing while the quote is still loading", () => {
    expect(
      renderHook(() => useQuoteChatOffers(CASE, undefined)).result.current,
    ).toEqual({});
  });

  it("a reminder only while the customer's answer on the spec is awaited, and never a reply", () => {
    const waiting = renderHook(() =>
      useQuoteChatOffers(CASE, "spec_discussion"),
    ).result.current;
    expect(waiting.customer_reminder).toBeTruthy();
    expect(waiting.reply_draft).toBeUndefined();
    const pricing = renderHook(() => useQuoteChatOffers(CASE, "pricing")).result
      .current;
    expect(pricing.customer_reminder).toBeUndefined();
    expect(pricing.thread_summary).toBeTruthy();
  });
});
