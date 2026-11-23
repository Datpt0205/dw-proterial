import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

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
const api = vi.hoisted(() => ({ lineTrail: vi.fn() }));
vi.mock("../api", () => ({ salesApi: () => api }));

import { LineTrail } from "../../_components/line-trail";

const TRAIL = {
  case_id: "c-1",
  line_no: 3,
  steps: [
    {
      kind: "read",
      code: "read",
      decided_by: "rule",
      cell: "PO!B12",
      at: "2026-11-02T03:00:00Z",
    },
    {
      kind: "model_reading",
      code: "sales.description_attributes@1.0.0",
      decided_by: "model",
      outcome: "read",
      confidence: 0.91,
      examples: 3,
    },
    {
      kind: "mapping",
      code: "mapping",
      decided_by: "dw",
      value: "HW-1001",
      outcome: "candidate_confirmed",
      at: "2026-11-02T03:05:00Z",
    },
    {
      kind: "finding",
      code: "requested_date_short_lt",
      decided_by: "rule",
      severity: "warning",
      rule_version: "sales.order_rules@1.2.0",
    },
    {
      kind: "finding_decided",
      code: "requested_date_short_lt",
      decided_by: "person",
      actor_user_id: AN,
      outcome: "accepted",
      at: "2026-11-02T04:00:00Z",
    },
  ],
};

afterEach(cleanup);

describe("LineTrail", () => {
  it("says who decided each step, in words, with its rule's code", async () => {
    api.lineTrail.mockResolvedValue(TRAIL);
    render(
      <UiProvider>
        <LineTrail kind="order" caseId="c-1" lineNo={3} version={4} />
      </UiProvider>,
    );
    expect(
      await screen.findByText(
        /5 bước: 2 do luật, 1 do mô hình, 1 DW tự áp dụng, 1 do người/,
      ),
    ).toBeTruthy();
    expect(api.lineTrail).toHaveBeenCalledWith("order", "c-1", 3);
    expect(screen.getAllByText("Luật")).toHaveLength(2);
    expect(screen.getByText("Mô hình")).toBeTruthy();
    expect(screen.getByText("DW tự áp dụng")).toBeTruthy();
    expect(screen.getByText("Người")).toBeTruthy();
    expect(
      screen.getByText("Phát hiện: Ngày yêu cầu ngắn hơn lead time"),
    ).toBeTruthy();
    expect(screen.getByText("Ô PO!B12")).toBeTruthy();
    // How many decided lines the model was shown beside the line (ticket 43).
    expect(screen.getByText(/đã xem 3 dòng đã quyết/)).toBeTruthy();
    expect(screen.getByText(/Chấp nhận \(có lý do\)/)).toBeTruthy();
    expect(
      screen.getByText("sales.order_rules@1.2.0", { exact: false }),
    ).toBeTruthy();
  });

  it("reads a quotation's line from the quote's own trail, outcomes in words", async () => {
    api.lineTrail.mockResolvedValue({
      case_id: "q-1",
      line_no: 1,
      steps: [
        {
          kind: "design_check",
          code: "design_check",
          decided_by: "person",
          value: "BP000001",
          outcome: "quote",
        },
        {
          kind: "declined",
          code: "decline",
          decided_by: "person",
          actor_user_id: AN,
          outcome: "commercial",
        },
      ],
    });
    render(
      <UiProvider>
        <LineTrail kind="quote" caseId="q-1" lineNo={1} version={2} />
      </UiProvider>,
    );
    expect(await screen.findByText("Kết quả Design trên Bravo")).toBeTruthy();
    expect(api.lineTrail).toHaveBeenCalledWith("quote", "q-1", 1);
    expect(screen.getByText(/Báo giá được · BP000001/)).toBeTruthy();
    expect(screen.getByText("Từ chối báo giá")).toBeTruthy();
    expect(screen.queryByText(/commercial/)).toBeNull();
  });

  it("shows the server's error, not an empty trail", async () => {
    api.lineTrail.mockRejectedValue(new Error("Máy chủ không trả lời"));
    render(
      <UiProvider>
        <LineTrail kind="order" caseId="c-1" lineNo={3} version={5} />
      </UiProvider>,
    );
    expect(await screen.findByRole("button", { name: /Thử lại/ })).toBeTruthy();
    expect(screen.queryByText(/bước:/)).toBeNull();
  });
});
