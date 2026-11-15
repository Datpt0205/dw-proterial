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

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
const api = vi.hoisted(() => ({
  items: vi.fn(async () => ({ items: [] })),
  rejectMapping: vi.fn(async (...args: unknown[]) => (void args, {})),
}));
vi.mock("../api", () => ({ salesApi: () => api }));

import { CandidatePicker } from "../../orders/[caseId]/candidate-picker";

type Line = SalesSchemas["OrderLineView"];
type Reading = NonNullable<Line["basis"]["description_reading"]>;

const READ: Reading = {
  prompt: "sales.description_attributes@1.0.0",
  model_profile: "onprem",
  outcome: "read",
  reason: null,
  spans: [],
};

/** The fixture's line 1 with model-proposed (or code-proposed) candidates. */
function withCandidates(codes: string[], reading: Reading | null = READ) {
  const base = order();
  const [line] = base.lines;
  if (line === undefined) throw new Error("the fixture order has no line");
  return order({
    lines: [
      {
        ...line,
        mapping: {
          ...line.mapping,
          status: codes.length > 1 ? "ambiguous" : "candidate",
          prv_code: null,
          candidates: codes,
        },
        basis: { ...line.basis, description_reading: reading },
      },
    ],
  });
}

function picker(data: ReturnType<typeof order>) {
  const onDone = vi.fn();
  const onClose = vi.fn();
  render(
    <UiProvider>
      <CandidatePicker
        order={data}
        lineNo={1}
        onClose={onClose}
        onDone={onDone}
        onOpenSource={() => {}}
      />
    </UiProvider>,
  );
  return { onDone, onClose };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('"Không phải mã này" (ticket 44)', () => {
  it("rejects a model's single candidate on the version seen and stays open", async () => {
    const data = withCandidates(["CB-2005"]);
    const { onDone, onClose } = picker(data);

    fireEvent.click(screen.getByRole("button", { name: "Không phải mã này" }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(api.rejectMapping).toHaveBeenCalledWith(
      data.case_id,
      1,
      { case_version: data.case_version },
      expect.any(String),
    );
    // The line is unmapped now: the picker stays to take a typed code.
    expect(onClose).not.toHaveBeenCalled();
  }, 30_000);

  it("rejects several candidates together", () => {
    picker(withCandidates(["CB-2001", "CB-2002"]));
    expect(
      screen.getByRole("button", { name: "Không phải các mã này" }),
    ).toBeTruthy();
  }, 30_000);

  it("is not offered for candidates no model proposed", () => {
    picker(withCandidates(["CB-2005"], null));
    expect(
      screen.queryByRole("button", { name: "Không phải mã này" }),
    ).toBeNull();
  }, 30_000);
});
