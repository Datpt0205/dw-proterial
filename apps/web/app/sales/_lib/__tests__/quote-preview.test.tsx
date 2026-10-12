import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Artifact } from "@dw/api-client";
import { GIANG, pendingQuote } from "./fixtures";

// Giang, the head, opens a quote Diệu submitted: he may approve it and render
// the preview.
const SCOPES = [
  "sales.case.read",
  "sales.price.read",
  "sales.quote.prepare",
  "sales.quote.approve",
  "approvals.decide",
];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: GIANG,
    displayName: "Giang",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: pendingQuote().case_id }),
}));

const quote = pendingQuote();
const preview: Artifact = {
  artifact_id: "01a10aa0-0000-7000-8000-00000000a001",
  case_version: quote.case_version,
  content_type: "application/pdf",
  created_at: "2026-10-05T05:00:00Z",
  created_by: GIANG,
  downloadable: true,
  file_name: "Q26-0301-preview.pdf",
  kind: "quotation_preview",
  sha256: "b".repeat(64),
  size_bytes: 2048,
  template_ref: "sales_documents@1.0.0",
} as Artifact;

// The server's file list: empty until a render succeeds, then the preview.
let stored: Artifact[] = [];
let renderFails = false;
const api = {
  quote: vi.fn(async () => quote),
  myWork: vi.fn(async () => []),
  customers: vi.fn(async () => ({ items: [] })),
  lme: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: quote.case_version,
    available: stored.length ? [] : ["quotation_preview"],
    artifacts: stored,
  })),
  renderArtifact: vi.fn(async () => {
    if (renderFails) throw new Error("render refused");
    stored = [preview];
    return { artifact_id: preview.artifact_id };
  }),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import QuotePage from "../../quotes/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <QuotePage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const RENDER = "Soạn Tài liệu báo giá (bản xem trước)";
const NO_PREVIEW = /^Chưa có bản xem trước ở phiên bản/;
const SHOW_PREVIEW = /Xem bản xem trước \(PDF/;
const DOWNLOAD_PREVIEW = "Tải Tài liệu báo giá (bản xem trước)";

afterEach(() => {
  cleanup();
  stored = [];
  renderFails = false;
  vi.clearAllMocks();
});

// The whole quote page draws: its first render in jsdom takes seconds.
const SLOW = 20_000;

describe("the quote approval panel and a preview rendered on the same page", () => {
  it(
    "offers the new preview once the artifacts panel renders it, without a reload",
    async () => {
      page();
      fireEvent.click(
        await screen.findByRole("button", { name: RENDER }, { timeout: 5000 }),
      );
      // The files panel lists the new preview...
      expect(
        await screen.findByRole(
          "button",
          { name: DOWNLOAD_PREVIEW },
          { timeout: 5000 },
        ),
      ).toBeTruthy();
      // ...and the approval panel, on the same page, offers it.
      expect(
        await screen.findByRole(
          "button",
          { name: SHOW_PREVIEW },
          { timeout: 5000 },
        ),
      ).toBeTruthy();
      expect(screen.queryByText(NO_PREVIEW)).toBeNull();
      // No reload of the page, and one read of the list per change.
      expect(api.quote).toHaveBeenCalledTimes(1);
      expect(api.artifacts).toHaveBeenCalledTimes(2);
    },
    SLOW,
  );

  it(
    "changes nothing in the approval panel when the render fails",
    async () => {
      renderFails = true;
      page();
      fireEvent.click(
        await screen.findByRole("button", { name: RENDER }, { timeout: 5000 }),
      );
      expect(
        await screen.findByText(/render refused/, undefined, { timeout: 5000 }),
      ).toBeTruthy();
      expect(screen.getByText(NO_PREVIEW)).toBeTruthy();
      expect(screen.queryByRole("button", { name: SHOW_PREVIEW })).toBeNull();
    },
    SLOW,
  );
});
