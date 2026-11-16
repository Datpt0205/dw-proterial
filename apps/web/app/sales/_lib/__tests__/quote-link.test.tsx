import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

let SCOPES = ["sales.case.read", "sales.order.prepare", "sales.quote.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const api = {
  openQuote: vi.fn(async () => ({
    case_version: 2,
    quote_case_id: "q-1",
    lines: [2],
  })),
  recheckQuotedLines: vi.fn(async () => ({ case_id: "c", case_version: 3 })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import {
  OpenQuoteButton,
  QuoteLinksPanel,
} from "../../orders/[caseId]/quote-link";

const viewer = () => ({
  principalId: AN,
  hasScope: (s: string) => SCOPES.includes(s),
});

const LINK = {
  quote_case_id: "q-1",
  lines: [2],
  by: AN,
  at: "2026-10-05T03:00:00Z",
  status: "ycbg_drafted",
  waiting: true,
};

function button(name: string): HTMLButtonElement {
  return screen
    .getByText(name, { selector: "button span" })
    .closest("button") as HTMLButtonElement;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  SCOPES = ["sales.case.read", "sales.order.prepare", "sales.quote.prepare"];
});

describe("Mở báo giá (ticket 09)", () => {
  it("opens the quote with the order's version, once per press", async () => {
    const shown = order({ status: "in_review" } as Partial<Order>);
    const onOpened = vi.fn();
    render(
      <UiProvider>
        <OpenQuoteButton order={shown} viewer={viewer()} onOpened={onOpened} />
      </UiProvider>,
    );

    fireEvent.click(button("Mở báo giá"));

    await waitFor(() => expect(onOpened).toHaveBeenCalled());
    expect(api.openQuote).toHaveBeenCalledWith(
      shown.case_id,
      shown.case_version,
      expect.any(String),
    );
  });

  it("is disabled, with the reason, while a quote from the order waits", () => {
    const shown = order({
      status: "in_review",
      quote_links: [LINK],
    } as Partial<Order>);
    render(
      <UiProvider>
        <OpenQuoteButton order={shown} viewer={viewer()} onOpened={vi.fn()} />
      </UiProvider>,
    );

    expect(button("Mở báo giá").disabled).toBe(true);
    expect(
      screen.getByText("Đã có hồ sơ báo giá mở từ đơn này, đang chờ duyệt."),
    ).toBeTruthy();
  });

  it("is disabled for a PIC who cannot open quotes", () => {
    SCOPES = ["sales.case.read", "sales.order.prepare"];
    render(
      <UiProvider>
        <OpenQuoteButton
          order={order({ status: "in_review" } as Partial<Order>)}
          viewer={viewer()}
          onOpened={vi.fn()}
        />
      </UiProvider>,
    );

    expect(button("Mở báo giá").disabled).toBe(true);
  });
});

describe("the quote cases opened from the order", () => {
  it("names the quote, its state and the wait, linked to its page", () => {
    render(
      <UiProvider>
        <QuoteLinksPanel
          order={order({ quote_links: [LINK] } as Partial<Order>)}
          viewer={viewer()}
          onChanged={vi.fn()}
        />
      </UiProvider>,
    );

    expect(screen.getByText("Đơn chờ báo giá")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Hồ sơ báo giá · dòng 2/ });
    expect(link.getAttribute("href")).toBe("/sales/quotes/q-1");
    expect(screen.getByText("Đã soạn YCBG")).toBeTruthy();
    expect(screen.queryByText("Kiểm tra lại theo báo giá")).toBeNull();
  });

  it("offers Kiểm tra lại once approved while the line still has no quotation", async () => {
    const shown = order({
      quote_links: [{ ...LINK, status: "approved", waiting: false }],
      findings: [
        {
          ...order().findings[0]!,
          code: "quotation_missing",
          key: "quotation_missing:2",
          line_no: 2,
        },
      ],
    } as Partial<Order>);
    const onChanged = vi.fn();
    render(
      <UiProvider>
        <QuoteLinksPanel
          order={shown}
          viewer={viewer()}
          onChanged={onChanged}
        />
      </UiProvider>,
    );

    expect(screen.queryByText("Đơn chờ báo giá")).toBeNull();
    fireEvent.click(button("Kiểm tra lại theo báo giá"));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.recheckQuotedLines).toHaveBeenCalled();
  });
});
