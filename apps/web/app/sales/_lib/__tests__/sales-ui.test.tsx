import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MASKED_LABEL, UiProvider } from "@dw/ui";

let principalId = "someone-else";
let scopes: string[] = [];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId,
    displayName: "Người xem",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
// No network: the roster and every Sales read answer from here.
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
vi.mock("../api", () => ({
  salesApi: () => ({
    artifacts: vi
      .fn()
      .mockResolvedValue({ case_version: 9, available: [], artifacts: [] }),
  }),
}));

import { FindingsPanel } from "../../orders/[caseId]/findings";
import { OrderActions } from "../../orders/[caseId]/actions";
import { ApprovalPanel } from "../../quotes/[caseId]/approval";
import { EvidencePanel } from "../../quotes/[caseId]/evidence";
import {
  Money,
  OTHER_CUSTOMERS_SENTENCE,
  PRICE_SENTENCE,
} from "../../_components/money";
import { MAKER_CHECKER, orderOffers } from "../order-actions";
import { approvalReason } from "../quote-actions";
import {
  AN,
  DIEU,
  finding,
  order,
  orderInBravo,
  pendingQuote,
} from "./fixtures";

const PIC = [
  "sales.overview.read",
  "sales.case.read",
  "sales.price.read",
  "sales.inbox.process",
  "sales.order.prepare",
  "sales.order.cross_check",
  "sales.quote.prepare",
  "sales.worker.pause",
];

function as(id: string, held: string[]) {
  principalId = id;
  scopes = held;
  return { principalId: id, hasScope: (scope: string) => held.includes(scope) };
}

function ui(node: ReactNode) {
  return render(<UiProvider>{node}</UiProvider>);
}

afterEach(() => {
  cleanup();
  principalId = "someone-else";
  scopes = [];
});

describe("a hidden amount", () => {
  it("is drawn locked as 'Đã ẩn', never as a figure, a zero or a dash", () => {
    const { container } = ui(<Money value={{ hidden: true }} currency="VND" />);
    expect(screen.getByText(MASKED_LABEL)).toBeTruthy();
    expect(container.textContent).not.toMatch(/\d|—/);
    expect(
      screen.getByRole("img", { name: `${MASKED_LABEL}. ${PRICE_SENTENCE}` }),
    ).toBeTruthy();
  });

  it("shows the figure when the API sent one", () => {
    const { container } = ui(<Money value="94115000" currency="VND" />);
    expect(container.textContent).toBe("94.115.000 đ");
    expect(screen.queryByText(MASKED_LABEL)).toBeNull();
  });

  it("locks other customers' prices as a region, with the sentence once", () => {
    const quote = pendingQuote();
    quote.evidence = [
      {
        line_no: 1,
        prv_code: "CB-2005",
        as_of: "2026-10-02",
        copper_usd_per_uom: "0.21",
        floor: "0.55",
        freight_usd_per_km: "1.2",
        lme: null,
        orders: [],
        own_history: [],
        other_customers: { hidden: true },
        pricing_policy: "sales_pricing@1.0.0",
        reference_price: { hidden: true },
        target_price: "0.65",
      },
    ];
    ui(<EvidencePanel quote={quote} />);
    expect(screen.getByText(OTHER_CUSTOMERS_SENTENCE)).toBeTruthy();
    expect(screen.getAllByText(MASKED_LABEL).length).toBeGreaterThanOrEqual(2);
  });

  it("locks the whole evidence when the viewer may not read prices", () => {
    const quote = pendingQuote();
    quote.evidence = { hidden: true };
    const { container } = ui(<EvidencePanel quote={quote} />);
    expect(screen.getByText(PRICE_SENTENCE)).toBeTruthy();
    expect(container.textContent).not.toMatch(/\d/);
  });
});

describe("the maker/checker rule on an order", () => {
  it("refuses the preparer's cross-check with the reason in words", () => {
    const viewer = as(AN, PIC);
    const offers = orderOffers(orderInBravo(), viewer, { sourceOpened: true });
    expect(offers.crossCheck?.reason).toBe(
      `Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (${MAKER_CHECKER}).`,
    );
    expect(MAKER_CHECKER).toBe("tách nhiệm, WIV-03-012 bước 9");
  });

  it("writes the reason beside the disabled button, not only in a tooltip", () => {
    const viewer = as(AN, PIC);
    ui(
      <OrderActions
        order={orderInBravo()}
        viewer={viewer}
        sourceOpened
        onChanged={() => {}}
      />,
    );
    const button = screen.getByRole("button", { name: "Kiểm chéo đạt" });
    expect(button.hasAttribute("disabled")).toBe(true);
    const note = screen
      .getAllByRole("note")
      .find((n) => n.textContent?.includes("tách nhiệm"));
    expect(note?.textContent).toContain(
      "Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được",
    );
    expect(button.getAttribute("aria-describedby")).toBe(note?.id);
  });

  it("lets someone who made none of it cross-check once the source is open", () => {
    const viewer = as(DIEU, PIC);
    ui(
      <OrderActions
        order={orderInBravo()}
        viewer={viewer}
        sourceOpened
        onChanged={() => {}}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Kiểm chéo đạt" })
        .hasAttribute("disabled"),
    ).toBe(false);
  });

  it("says 'Chưa mở nguồn' to a checker who has not opened the original", () => {
    const viewer = as(DIEU, PIC);
    const offers = orderOffers(orderInBravo(), viewer, { sourceOpened: false });
    expect(offers.crossCheck?.reason).toMatch(/^Chưa mở nguồn/);
  });

  it("names the open findings that block preparation", () => {
    const viewer = as(AN, PIC);
    const blocked = order({
      findings: [
        finding(),
        finding({ key: "moq_violation:1", code: "moq_violation", line_no: 1 }),
      ],
    });
    expect(
      orderOffers(blocked, viewer, { sourceOpened: true }).prepare?.reason,
    ).toBe("Còn 2 cờ chưa quyết định.");
  });
});

describe("the pricer/approver rule on a quote", () => {
  it("refuses the pricer's approval with the reason in words", () => {
    const head = as(DIEU, [...PIC, "sales.quote.approve"]);
    expect(approvalReason(pendingQuote(), head)).toBe(
      "Bạn đã định giá báo giá này nên không tự duyệt được (tách nhiệm, WIV-03-023 bước 9).",
    );
  });

  it("refuses someone without the approve scope before anything else", () => {
    const pic = as(DIEU, PIC);
    expect(approvalReason(pendingQuote(), pic)).toMatch(
      /^Bạn không có quyền duyệt báo giá/,
    );
  });

  it("draws the approval disabled for the pricer, with the reason beside it", () => {
    const pricer = as(DIEU, [...PIC, "sales.quote.approve"]);
    ui(
      <ApprovalPanel
        quote={pendingQuote()}
        viewer={pricer}
        onDone={() => {}}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: "Duyệt báo giá" })
        .hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen
        .getAllByRole("note")
        .some((n) => n.textContent?.includes("tách nhiệm, WIV-03-023 bước 9")),
    ).toBe(true);
  });
});

describe("per-finding decisions", () => {
  const twoOpen = order({
    findings: [
      finding(),
      finding({
        key: "moq_violation:1",
        code: "moq_violation",
        line_no: 1,
        allowed: ["accepted", "ask_customer"],
      }),
      finding({
        key: "missing_noc_esf:-",
        code: "missing_noc_esf",
        blocking: false,
        severity: "warning",
        line_no: null,
        allowed: ["accepted"],
      }),
    ],
  });

  it("offers no bulk decision: no 'tất cả', and one control per open finding", () => {
    const viewer = as(AN, PIC);
    ui(
      <FindingsPanel
        order={twoOpen}
        viewer={viewer}
        onChanged={() => {}}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />,
    );
    expect(screen.queryByText(/tất cả/i)).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(
      screen.getAllByRole("radiogroup", { name: "Quyết định cho cờ này" }),
    ).toHaveLength(2);
    expect(screen.getByRole("status").textContent).toBe(
      "Còn 3 cờ chưa quyết định (2 chặn)",
    );
  });

  it("offers only the dispositions the code allows", () => {
    const viewer = as(AN, PIC);
    const only = order({ findings: [finding({ allowed: ["ask_customer"] })] });
    ui(
      <FindingsPanel
        order={only}
        viewer={viewer}
        onChanged={() => {}}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />,
    );
    const group = screen.getByRole("radiogroup", {
      name: "Quyết định cho cờ này",
    });
    expect(within(group).queryByText("Chấp nhận + lý do")).toBeNull();
    expect(within(group).getByText("Yêu cầu khách sửa")).toBeTruthy();
  });

  it("asks for a reason before an acceptance is sent", async () => {
    const viewer = as(AN, PIC);
    ui(
      <FindingsPanel
        order={order({ findings: [finding()] })}
        viewer={viewer}
        onChanged={() => {}}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />,
    );
    // Nothing is chosen until the person chooses: no decision is pre-selected.
    expect(
      screen.getByRole("radio", { name: "Chấp nhận + lý do" }),
    ).toHaveProperty("checked", false);
    fireEvent.click(screen.getByRole("radio", { name: "Chấp nhận + lý do" }));
    expect(await screen.findByLabelText("Lý do chấp nhận")).toBeTruthy();
  });

  it("keeps NOC/ESF for the export-control PIC, saying so to anyone else", () => {
    const viewer = as(DIEU, PIC);
    ui(
      <FindingsPanel
        order={twoOpen}
        viewer={viewer}
        onChanged={() => {}}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />,
    );
    expect(
      screen.getByText("Chỉ PIC kiểm soát xuất khẩu xác nhận cờ này."),
    ).toBeTruthy();
  });
});
