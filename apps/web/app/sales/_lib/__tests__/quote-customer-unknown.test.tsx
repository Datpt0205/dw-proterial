import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { pendingQuote } from "./fixtures";

vi.mock("../people", () => ({ usePeople: () => (id: string) => id }));
vi.mock("../api", () => ({ salesApi: () => ({ answerFinding: vi.fn() }) }));

import { QuoteActions } from "../../quotes/[caseId]/actions";

type Quote = SalesSchemas["QuoteCaseView"];

function forwarded(): Quote {
  return {
    ...pendingQuote(),
    status: "received",
    customer_code: "VLX",
    sender: "sales.manager@seller.example",
    findings: [
      {
        key: "customer_unknown",
        code: "customer_unknown",
        line_no: null,
        missing: [],
        blocking: true,
        disposition: { kind: "open" },
      },
    ],
  } as unknown as Quote;
}

const viewer = {
  principalId: "u-an",
  hasScope: () => true,
} as unknown as Parameters<typeof QuoteActions>[0]["viewer"];

afterEach(cleanup);

describe("a request forwarded from the Sales mailbox (2026-10-28)", () => {
  it("fills in the customer DW1 read and says why a person confirms it", () => {
    render(
      <UiProvider>
        <QuoteActions
          quote={forwarded()}
          viewer={viewer}
          onDone={() => undefined}
        />
      </UiProvider>,
    );
    const code = screen.getByLabelText("Mã khách hàng") as HTMLInputElement;
    expect(code.value).toBe("VLX");
    expect(
      screen.getByText(
        /Thư gửi từ sales\.manager@seller\.example, không phải từ địa chỉ của khách/,
      ),
    ).toBeTruthy();
  });
});
