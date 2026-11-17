import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { DIEU, pendingQuote } from "./fixtures";
import { PcsPricePanel } from "../../quotes/[caseId]/pcs-price";

const scopes = vi.hoisted(() => ({ prepare: true }));
const api = vi.hoisted(() => ({
  productionType: vi.fn(),
  pcsPrice: vi.fn(),
  pcsPriceRequest: vi.fn(),
}));

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: DIEU,
    displayName: "Diệu",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope !== "sales.quote.prepare" || scopes.prepare,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
vi.mock("../api", () => ({ salesApi: () => api }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes.prepare = true;
});

function waiting() {
  return {
    ...pendingQuote(),
    status: "design_replied",
    pricing: null,
    production_type: "pcs",
    production_type_set: { by: DIEU, at: "2026-11-16T02:00:00Z" },
    waits_on_pcs_price: true,
    pcs_price: null,
  };
}

function draw(quote: ReturnType<typeof waiting>) {
  return render(
    <UiProvider>
      <PcsPricePanel quote={quote} onDone={() => {}} />
    </UiProvider>,
  );
}

describe("ticket 05: a pcs case waits for the GM's price", () => {
  it("says the case waits on the GM and offers the GM's price per line", () => {
    draw(waiting());
    expect(screen.getByText(/cần giá GM\/BC Manager/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ghi giá GM" })).toBeTruthy();
  });

  it("records the GM's price for every line as the caller", async () => {
    api.pcsPrice.mockResolvedValue({});
    const quote = waiting();
    draw(quote);
    for (const line of quote.lines) {
      fireEvent.change(screen.getByLabelText(`Giá GM dòng ${line.line_no}`), {
        target: { value: "12,40" },
      });
    }
    fireEvent.click(screen.getByRole("button", { name: "Ghi giá GM" }));
    await waitFor(() => expect(api.pcsPrice).toHaveBeenCalledTimes(1));
    const [, body] = api.pcsPrice.mock.calls[0];
    expect(body.lines.map((l: { line_no: number }) => l.line_no)).toEqual(
      quote.lines.map((l) => l.line_no),
    );
    expect(Object.keys(body)).not.toContain("recorded_by");
  });

  it("a caller without the prepare scope records nothing and cannot switch the type", () => {
    scopes.prepare = false;
    draw(waiting());
    expect(screen.queryByRole("button", { name: "Ghi giá GM" })).toBeNull();
    expect(
      screen.getByRole("radio", { name: "Mass", hidden: true }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("the GM's price stays hidden from a caller who may not read prices", () => {
    draw({
      ...waiting(),
      waits_on_pcs_price: false,
      pcs_price: {
        lines: [{ line_no: 1, unit_price: { hidden: true } }],
        recorded_by: DIEU,
        recorded_at: "2026-11-16T03:00:00Z",
      },
    } as unknown as ReturnType<typeof waiting>);
    expect(screen.queryByText(/12[.,]4/)).toBeNull();
    expect(screen.queryByText(/cần giá GM\/BC Manager/)).toBeNull();
  });
});
