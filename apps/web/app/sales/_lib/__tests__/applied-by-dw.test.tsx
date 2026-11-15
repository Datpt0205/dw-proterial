import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN, order } from "./fixtures";

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
const api = vi.hoisted(() => ({
  undoMapping: vi.fn(async (...args: unknown[]) => (void args, {})),
}));
vi.mock("../api", () => ({ salesApi: () => api }));

import { LinesTable } from "../../orders/[caseId]/lines";

const LANE = "6d1f9c3e-5b6a-5c5e-9d1e-3f0a7c2b4e11";

/** The fixture's line 1, its code confirmed by DW itself or by a person. */
function confirmed(byDw: boolean) {
  const base = order();
  const [line] = base.lines;
  if (line === undefined) throw new Error("the fixture order has no line");
  return order({
    lines: [
      {
        ...line,
        mapping: {
          status: "candidate_confirmed",
          prv_code: "HW-1001",
          candidates: ["HW-1001"],
          confirmed_by: byDw ? LANE : AN,
          confirmed_at: "2026-11-16T03:00:00Z",
          hand_entered: false,
          applied_by_dw: byDw,
        },
      },
    ],
  });
}

function cells(data: ReturnType<typeof order>, canPrepare = true) {
  const onChanged = vi.fn();
  render(
    <UiProvider>
      <LinesTable
        order={data}
        viewer={{ principalId: AN, hasScope: () => canPrepare }}
        onChanged={onChanged}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />
    </UiProvider>,
  );
  const tr = screen
    .getByRole("button", { name: "Xem nguồn dòng 1" })
    .closest("tr")!;
  return { row: within(tr as HTMLElement), onChanged };
}

// Antd's table renders slowly in jsdom.
const SLOW = 30_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a code DW applied by itself (ticket 44)", () => {
  it(
    "says DW did it and undoes it in one press",
    async () => {
      const data = confirmed(true);
      const { row, onChanged } = cells(data);

      expect(row.getByText("DW đã tự làm")).toBeTruthy();
      fireEvent.click(row.getByRole("button", { name: "Hoàn tác" }));

      await waitFor(() => expect(onChanged).toHaveBeenCalled());
      expect(api.undoMapping).toHaveBeenCalledWith(
        data.case_id,
        1,
        { case_version: data.case_version },
        expect.any(String),
      );
    },
    SLOW,
  );

  it(
    "offers no undo for a code a person confirmed",
    () => {
      const { row } = cells(confirmed(false));
      expect(row.queryByText("DW đã tự làm")).toBeNull();
      expect(row.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
    },
    SLOW,
  );

  it(
    "keeps the undo disabled for someone who may not change the code",
    () => {
      const { row } = cells(confirmed(true), false);
      const undo = row.getByRole("button", { name: "Hoàn tác" });
      expect((undo as HTMLButtonElement).disabled).toBe(true);
    },
    SLOW,
  );
});
