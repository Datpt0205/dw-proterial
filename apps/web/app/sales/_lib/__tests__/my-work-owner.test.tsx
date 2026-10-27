import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type WorkItem = SalesSchemas["WorkItem"];

const SCOPES = ["sales.case.read"];
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
vi.mock("next/navigation", () => ({
  usePathname: () => "/sales",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const mail = (id: string, owner: string): WorkItem => ({
  kind: "message",
  id,
  status: "routed",
  action: "triage",
  customer_code: null,
  received_at: "2026-10-27T01:00:00Z",
  due: null,
  assigned_to: null,
  owner,
});
let items: WorkItem[] = [];
const api = {
  myWork: vi.fn(async () => items),
  orders: vi.fn(async () => []),
  quotes: vi.fn(async () => []),
  inbox: vi.fn(async () => []),
  openYcbg: vi.fn(async () => []),
  customers: vi.fn(async () => ({ items: [] })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import MyWorkPage from "../../page";
import { SalesFrameProvider } from "../../_components/sales-frame";

afterEach(() => {
  cleanup();
  items = [];
});

describe("a routed mail on Việc cần làm (2026-10-27)", () => {
  it(
    "names its owner as the inbox does: a person, or the team",
    async () => {
      items = [mail("m-1", AN), mail("m-2", "role:sales_admin")];
      render(
        <UiProvider>
          <SalesFrameProvider>
            <MyWorkPage />
          </SalesFrameProvider>
        </UiProvider>,
      );
      expect(
        await screen.findByRole("img", { name: "Phụ trách: An (bạn)" }),
      ).toBeTruthy();
      expect(
        screen.getByRole("img", { name: /^Phụ trách: Cả nhóm / }),
      ).toBeTruthy();
      expect(screen.queryByText("Chưa giao")).toBeNull();
    },
    20_000,
  );
});
