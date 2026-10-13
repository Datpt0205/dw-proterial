import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN, finding, order } from "./fixtures";

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
vi.mock("../api", () => ({ salesApi: () => ({}) }));

import { FindingsPanel } from "../../orders/[caseId]/findings";

const PIC = { principalId: AN, hasScope: () => true };

/** A PO typed in `.VnTime` (ticket 20): one finding about the whole PO. */
const legacy = order({
  findings: [
    finding({
      key: "legacy_encoding:-",
      code: "legacy_encoding",
      line_no: null,
      expected: "Unicode",
      actual: "TCVN3",
      allowed: ["ask_customer"],
    }),
  ],
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a PO typed in a legacy Vietnamese font (ticket 20)", () => {
  it("offers only asking the customer, and says why nothing else is offered", () => {
    render(
      <UiProvider>
        <FindingsPanel
          order={legacy}
          viewer={PIC}
          onChanged={() => {}}
          onOpenSource={() => {}}
          onPickCode={() => {}}
        />
      </UiProvider>,
    );
    const group = screen.getByRole("radiogroup", {
      name: "Quyết định cho cờ này",
    });
    expect(within(group).getAllByRole("radio")).toHaveLength(1);
    expect(within(group).getByText("Yêu cầu khách sửa")).toBeTruthy();
    expect(screen.getByText(/Không sửa tay được/)).toBeTruthy();
    expect(screen.getByText("Font tiếng Việt cũ (TCVN3/VNI)")).toBeTruthy();
  }, 20_000);

  it("opens the source at the first value typed in that font", () => {
    const onOpenSource = vi.fn();
    render(
      <UiProvider>
        <FindingsPanel
          order={legacy}
          viewer={PIC}
          onChanged={() => {}}
          onOpenSource={onOpenSource}
          onPickCode={() => {}}
        />
      </UiProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Xem nguồn/ }));
    expect(onOpenSource).toHaveBeenCalledWith("legacy_text", null);
  }, 20_000);
});
