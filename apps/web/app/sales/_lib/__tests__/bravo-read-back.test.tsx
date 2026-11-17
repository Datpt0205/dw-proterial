import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";
import { BravoReadBackPanel } from "../../orders/[caseId]/bravo-read-back";

type View = SalesSchemas["ReadBackView"];

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

let shown: View;
vi.mock("../api", () => ({
  salesApi: () => ({ bravoReadBack: vi.fn(async () => shown) }),
}));

function differs(stale: boolean): View {
  return {
    read_back: {
      case_id: "c-1",
      case_version: 7,
      differences: [{ po_no: "PO-1", line_no: 1, field: "missing_row" }],
      file_sha256: "0".repeat(64),
      po_no: "PO-1",
      read_at: "2026-11-17T02:00:00Z",
      read_by: AN,
      rows_read: 1,
      so_no: "SO-2611-0042",
    },
    stale,
    prices_hidden: false,
  } as View;
}

const BLOCKS = /Chưa thể kiểm chéo đạt/;

afterEach(cleanup);

describe("ticket 03: a read-back that differs blocks the cross-check", () => {
  it("says so beside the difference at the case's current version", async () => {
    shown = differs(false);
    render(
      <UiProvider>
        <BravoReadBackPanel caseId="c-1" />
      </UiProvider>,
    );
    expect(await screen.findByText(BLOCKS)).toBeTruthy();
  });

  it("says nothing of a block once the case changed after the read", async () => {
    shown = differs(true);
    render(
      <UiProvider>
        <BravoReadBackPanel caseId="c-1" />
      </UiProvider>,
    );
    expect(
      await screen.findByText(/Hồ sơ đã đổi sau lần đọc này/),
    ).toBeTruthy();
    expect(screen.queryByText(BLOCKS)).toBeNull();
  });
});
