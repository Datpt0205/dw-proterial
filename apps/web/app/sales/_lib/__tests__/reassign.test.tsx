import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN, DIEU, GIANG } from "./fixtures";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: GIANG,
    displayName: "Giang",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
const api = {
  assignees: vi.fn(async () => [
    { user_id: AN, display_name: "Nguyễn Văn An" },
    { user_id: DIEU, display_name: "Hoàng Thị Diệu" },
  ]),
  reassign: vi.fn(async () => ({
    case_kind: "order",
    case_id: "c-1",
    case_version: 4,
    status: "in_review",
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { ReassignButton } from "../../_components/reassign";

const CASE = "01a10aa0-c939-7000-8539-31fd3e621660";

function control(scopes: string[], onDone = () => {}) {
  return render(
    <UiProvider>
      <ReassignButton
        kind="order"
        caseId={CASE}
        caseVersion={3}
        assignedTo={AN}
        viewer={{
          principalId: GIANG,
          hasScope: (s: string) => scopes.includes(s),
        }}
        onDone={onDone}
      />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Phân công lại (ticket 17)", () => {
  it("is not drawn for someone without sales.case.assign", () => {
    control(["sales.case.read", "sales.order.prepare"]);
    expect(screen.queryByRole("button", { name: "Phân công lại" })).toBeNull();
    expect(api.assignees).not.toHaveBeenCalled();
  });

  it("gives the case to a member the API offered, with the version and a key", async () => {
    const onDone = vi.fn();
    control(["sales.case.assign"], onDone);
    fireEvent.click(screen.getByRole("button", { name: "Phân công lại" }));
    fireEvent.mouseDown(
      await screen.findByRole("combobox", undefined, { timeout: 5000 }),
    );
    fireEvent.click(
      await screen.findByText("Hoàng Thị Diệu", undefined, { timeout: 5000 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Phân công" }));
    await waitFor(() => expect(api.reassign).toHaveBeenCalledTimes(1), {
      timeout: 5000,
    });
    const [kind, caseId, body, key] = api.reassign.mock.calls[0] as unknown as [
      string,
      string,
      unknown,
      string,
    ];
    expect([kind, caseId, body]).toEqual([
      "order",
      CASE,
      { assignee: DIEU, case_version: 3 },
    ]);
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(onDone).toHaveBeenCalled(), { timeout: 5000 });
  }, 20_000);
});
