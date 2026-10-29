import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

const scopes = vi.hoisted(() => ({ held: ["platform.tenant.settings.write"] }));
vi.mock("../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    hasScope: (scope: string) => scopes.held.includes(scope),
  }),
}));

const stopped = {
  id: "e-1",
  event_type: "sales.catalog.imported",
  occurred_at: "2026-10-29T02:00:00Z",
  attempts: 5,
  error_kind: "ReaderUnavailableError",
};
const listBackgroundFailures = vi.fn(async () => [stopped]);
const retryBackgroundFailure = vi.fn(async (_id: string) => undefined);
vi.mock("../../../lib/session", () => ({
  apiClient: () => ({ listBackgroundFailures, retryBackgroundFailure }),
}));

import BackgroundFailuresPage from "../background-failures/page";

afterEach(() => {
  cleanup();
  scopes.held = ["platform.tenant.settings.write"];
});

describe("background work that stopped (2026-10-29)", () => {
  it("lists what stopped and runs one again", async () => {
    render(
      <UiProvider>
        <BackgroundFailuresPage />
      </UiProvider>,
    );
    expect(await screen.findByText("sales.catalog.imported")).toBeTruthy();
    expect(screen.getByText("ReaderUnavailableError")).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", { name: "Chạy lại sales.catalog.imported" }),
    );
    await waitFor(() =>
      expect(retryBackgroundFailure).toHaveBeenCalledWith("e-1"),
    );
  });

  it("is closed to someone who does not administer the company", () => {
    scopes.held = [];
    render(
      <UiProvider>
        <BackgroundFailuresPage />
      </UiProvider>,
    );
    expect(screen.getByText(/Cần quyền quản trị công ty/)).toBeTruthy();
    expect(screen.queryByText("sales.catalog.imported")).toBeNull();
  });
});
