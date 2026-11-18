import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { DIEU, pendingQuote } from "./fixtures";
import { DesignFromBravo } from "../../quotes/[caseId]/design-check";

const scopes = vi.hoisted(() => ({ prepare: true }));
const api = vi.hoisted(() => ({ designFromBravo: vi.fn() }));

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: DIEU,
    displayName: "Diệu",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) =>
      scope !== "sales.quote.prepare" || scopes.prepare,
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

function waiting(verdict: "quote" | "decline" = "quote") {
  return {
    ...pendingQuote(),
    status: "sent_to_design",
    case_version: 7,
    design_check: {
      ycbg_no: "RFQ261110-003",
      file_sha256: "0".repeat(64),
      read_by: DIEU,
      read_at: "2026-11-17T02:00:00Z",
      lines: [
        {
          line_no: 1,
          verdict,
          bp_code: verdict === "quote" ? "BP003833" : null,
          reason: verdict === "quote" ? null : "không làm được",
        },
      ],
      snapshot: {
        file_sha256: "0".repeat(64),
        sheet: "RFQ List",
        rows: [
          { row: 2, cells: ["RFQ No"] },
          { row: 4, cells: ["RFQ261110-003"] },
        ],
      },
    },
  } as unknown as Parameters<typeof DesignFromBravo>[0]["quote"];
}

function draw(quote: ReturnType<typeof waiting>, onOpenRows = vi.fn()) {
  render(
    <UiProvider>
      <DesignFromBravo
        quote={quote}
        onOpenRows={onOpenRows}
        onDone={() => {}}
      />
    </UiProvider>,
  );
  return onOpenRows;
}

const USE = "Dùng kết quả Design trên Bravo";

describe("ticket 11: Design's result on Bravo recorded as its reply", () => {
  it("opens the request's rows and records the result on the version shown", async () => {
    api.designFromBravo.mockResolvedValue({});
    const opened = draw(waiting());
    fireEvent.click(screen.getByRole("button", { name: "Mở các dòng YCBG" }));
    expect(opened).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: USE }));
    await waitFor(() => expect(api.designFromBravo).toHaveBeenCalledTimes(1));
    const [, body] = api.designFromBravo.mock.calls[0] ?? [];
    expect(body).toEqual({ case_version: 7 });
  });

  it("is disabled, with the reason, over a decline or without the prepare scope", () => {
    draw(waiting("decline"));
    expect(
      screen.getByRole("button", { name: USE }).hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen.getAllByText(/Design từ chối một dòng/).length,
    ).toBeGreaterThan(0);
    cleanup();

    scopes.prepare = false;
    draw(waiting());
    expect(
      screen.getByRole("button", { name: USE }).hasAttribute("disabled"),
    ).toBe(true);
  });
});
