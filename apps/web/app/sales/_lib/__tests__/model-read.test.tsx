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
import { AN, pendingQuote } from "./fixtures";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
const api = {
  quoteMessageText: vi.fn(async () => ({
    case_id: "c-1",
    case_version: 2,
    text: TEXT,
    sha256: "a".repeat(64),
    served_at: "2026-10-03T02:00:00Z",
  })),
  answerFinding: vi.fn(async () => ({
    case_kind: "quote",
    case_id: "c-1",
    case_version: 3,
    status: "received",
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import {
  MessageTextDrawer,
  ModelReadFinding,
} from "../../quotes/[caseId]/model-read";
import { quoteTitle } from "../quote-actions";

type Quote = SalesSchemas["QuoteCaseView"];
type Finding = SalesSchemas["QuoteFindingView"];

const TEXT =
  "Yêu cầu báo giá\n\n1. Cáp 2C AWG24 BLK, 1.200 m, cần trước 15/11\nGiá tính bằng USD.";

/** M37 as a model read it: a request in the mail, no file, no number. */
function m37(): Quote {
  return {
    ...pendingQuote(),
    status: "received",
    case_version: 2,
    rfq_no: null,
    rfq_date: null,
    attachment_id: null,
    attachment_sha256: null,
    model_read: ["currency"],
    reading: {
      prompt: "sales.rfq_extraction@1.0.0",
      model_profile: "onprem",
      route: "structured_extraction",
      rules: "sales_order_rules@1.3.1",
      calls: 1,
      refused: {},
    },
    lines: [
      {
        line_no: 1,
        customer_item_code: null,
        description: "Cáp 2C AWG24 BLK",
        quantity: "1200",
        uom: "m",
        target_price: null,
        needed_by: "2026-11-15",
        anchors: {},
        model_read: ["description", "needed_by", "quantity", "uom"],
        candidates: [],
      },
    ],
    pricing: null,
    submission: null,
    decision: null,
  };
}

function uncertain(): Finding {
  return {
    key: "value_uncertain:1",
    code: "value_uncertain",
    blocking: true,
    line_no: 1,
    missing: [],
    flagged: ["description", "needed_by", "quantity", "uom"],
    confirmed: [
      {
        field: "description",
        read: "Cáp 2C AWG24 BLK",
        value: "Cáp 2C AWG24 BLK",
        by: AN,
        at: "2026-10-03T02:00:00Z",
      },
    ],
    expected: null,
    actual: null,
    rule_versions: [],
    disposition: { kind: "open" },
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a value a model read, confirmed one by one (ticket 29)", () => {
  it("shows each flagged value, says which are confirmed, and posts one field", async () => {
    const onDone = vi.fn();
    render(
      <UiProvider>
        <ModelReadFinding
          quote={m37()}
          finding={uncertain()}
          viewer={{ principalId: AN, hasScope: () => true } as never}
          onDone={onDone}
          name={() => "An"}
        />
      </UiProvider>,
    );
    expect(screen.getByText(/Đã xác nhận: Cáp 2C AWG24 BLK/)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Xác nhận" })).toHaveLength(3);
    // No bulk action: one button per value, nothing that confirms them all.
    expect(screen.queryByRole("button", { name: /tất cả/i })).toBeNull();

    const uom = screen.getByRole("textbox", { name: "Đơn vị tính xác nhận" });
    fireEvent.change(uom, { target: { value: "m" } });
    const buttons = screen.getAllByRole("button", { name: "Xác nhận" });
    fireEvent.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(api.answerFinding).toHaveBeenCalledTimes(1), {
      timeout: 5000,
    });
    const [caseId, key, body] = api.answerFinding.mock.calls[0] as unknown as [
      string,
      string,
      unknown,
    ];
    expect([caseId, key, body]).toEqual([
      m37().case_id,
      "value_uncertain:1",
      { case_version: 2, field: "uom", value: "m" },
    ]);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  }, 20_000);

  it("asks the server for the mail when opened, and highlights the value's words", async () => {
    const start = TEXT.indexOf("1.200 m");
    render(
      <UiProvider>
        <MessageTextDrawer
          quote={m37()}
          target={{ field: "quantity", lineNo: 1, start, end: start + 7 }}
          mayRead
          onClose={() => {}}
        />
      </UiProvider>,
    );
    // Served by its own route, which records the opening (ticket 29).
    await waitFor(() =>
      expect(document.querySelector("mark")?.textContent).toBe("1.200 m"),
    );
    expect(api.quoteMessageText).toHaveBeenCalledWith(m37().case_id);
  }, 20_000);

  it("asks nothing while closed", () => {
    render(
      <UiProvider>
        <MessageTextDrawer
          quote={m37()}
          target={null}
          mayRead
          onClose={() => {}}
        />
      </UiProvider>,
    );
    expect(api.quoteMessageText).not.toHaveBeenCalled();
  });

  it("tells who may not read prices why the mail is not shown, without asking", () => {
    render(
      <UiProvider>
        <MessageTextDrawer
          quote={m37()}
          target={{ field: "quantity", lineNo: 1, start: 0, end: 4 }}
          mayRead={false}
          onClose={() => {}}
        />
      </UiProvider>,
    );
    expect(screen.getByText(/quyền xem giá/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("1.200 m");
    expect(api.quoteMessageText).not.toHaveBeenCalled();
  }, 20_000);

  it("names a request that states no number by the mail it came in", () => {
    expect(quoteTitle(m37())).toBe("Yêu cầu trong thư 30/09/2026");
    expect(quoteTitle(pendingQuote())).toBe("RFQ KMH-RFQ-260930-02");
  });
});
