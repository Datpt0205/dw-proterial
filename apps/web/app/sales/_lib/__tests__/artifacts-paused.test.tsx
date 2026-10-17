import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Artifact } from "@dw/api-client";
import { AN, GIANG } from "./fixtures";

// An, a PIC who may render and see prices, and read the overview (DW1's state).
const SCOPES = [
  "sales.case.read",
  "sales.price.read",
  "sales.order.prepare",
  "sales.overview.read",
];
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

const CASE_ID = "01a10aa0-0000-7000-8000-0000000000c1";
const upload: Artifact = {
  artifact_id: "01a10aa0-0000-7000-8000-00000000a002",
  case_version: 3,
  content_type:
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  created_at: "2026-10-05T05:00:00Z",
  created_by: AN,
  downloadable: true,
  file_name: `bravo_upload-${CASE_ID}.xlsx`,
  kind: "bravo_upload",
  sha256: "c".repeat(64),
  size_bytes: 4096,
  template_ref: "sales_bravo_upload@1.1.0",
} as Artifact;

let paused = false;
const api = {
  overview: vi.fn(async () => ({
    worker: {
      paused,
      changed_by: GIANG,
      changed_at: "2026-10-18T02:00:00Z",
      reason: null,
    },
  })),
  artifacts: vi.fn(async () => ({
    case_version: 3,
    available: ["bravo_upload", "cross_check_sheet"],
    artifacts: [upload],
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import {
  ArtifactsPanel,
  useCaseArtifacts,
} from "../../_components/artifacts-panel";
import {
  PAUSED_REASON,
  SalesFrameProvider,
} from "../../_components/sales-frame";

function Panel() {
  const list = useCaseArtifacts("order", CASE_ID, 3);
  return (
    <ArtifactsPanel
      kind="order"
      caseId={CASE_ID}
      caseVersion={3}
      canRender
      renderReason="no scope"
      list={list}
    />
  );
}

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <Panel />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const RENDER = /Soạn .*kiểm chéo/;
const DOWNLOAD = /^Tải /;

afterEach(() => {
  cleanup();
  paused = false;
  vi.clearAllMocks();
});

describe("rendering while DW1 is paused (Đạt, 2026-10-18)", () => {
  it("refuses a render, says why, and still downloads what exists", async () => {
    paused = true;
    page();
    await screen.findByText("DW1 đang tạm dừng");
    // The frame says what a pause stops: files and drafts too.
    expect(screen.getByText(/không soạn tệp hay thư nháp/)).toBeTruthy();
    const button = await screen.findByRole("button", { name: RENDER });
    await waitFor(() => expect(button.hasAttribute("disabled")).toBe(true));
    expect(
      (await screen.findByRole("button", { name: DOWNLOAD })).hasAttribute(
        "disabled",
      ),
    ).toBe(false);
    expect(PAUSED_REASON).toMatch(/^DW1 đang tạm dừng/);
  }, 20_000);

  it("offers the render while DW1 runs", async () => {
    page();
    await screen.findByText(/DW1 đang chạy/);
    const button = await screen.findByRole("button", { name: RENDER });
    expect(button.hasAttribute("disabled")).toBe(false);
  }, 20_000);
});
