import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

let scopes = ["sales.case.read", "sales.quote.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

const designTextReply = vi.fn();
const confirmDesignTextReply = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ designTextReply, confirmDesignTextReply }),
}));

import { DesignTextPanel } from "../../inbox/design-text";

const LINE = {
  line_no: 1,
  bp_code: "BP-2609-030-01",
  spec_no: "SP-2609-030-01",
  prv_code: "CB-2006",
  copper_kg_per_km: "38.4",
};
const READ = {
  message_id: "D01",
  status: "read",
  ycbg_no: "YCBG-2609-030",
  case_id: "c-1",
  lines: [LINE],
  prompt_ref: "sales.design_text_reply@1.0.0",
  model_profile: "onprem",
};

afterEach(() => {
  cleanup();
  designTextReply.mockReset();
  confirmDesignTextReply.mockReset();
  scopes = ["sales.case.read", "sales.quote.prepare"];
});

function renderIt(onAttached = vi.fn()) {
  render(
    <UiProvider>
      <DesignTextPanel messageId="D01" onAttached={onAttached} />
    </UiProvider>,
  );
  return onAttached;
}

describe("DW1 đọc thư Design viết tay (AI item 6)", () => {
  it("shows the machine's reading and attaches it only when Sales confirms", async () => {
    designTextReply.mockResolvedValue(READ);
    confirmDesignTextReply.mockResolvedValue({ case_id: "c-1" });
    const onAttached = renderIt();
    expect(await screen.findByText("Máy đọc")).toBeTruthy();
    expect(screen.getByText("BP-2609-030-01")).toBeTruthy();
    expect(confirmDesignTextReply).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Xác nhận trả lời của Design trong thư D01",
      }),
    );
    await waitFor(() => expect(onAttached).toHaveBeenCalled());
    expect(confirmDesignTextReply).toHaveBeenCalledWith(
      "D01",
      { ycbg_no: "YCBG-2609-030", lines: [LINE] },
      expect.any(String),
    );
  });

  it("says when no case waits on Design under the number", async () => {
    designTextReply.mockResolvedValue({
      ...READ,
      status: "no_case",
      lines: [],
    });
    renderIt();
    expect(
      await screen.findByText(/không có hồ sơ nào đang chờ Design/),
    ).toBeTruthy();
  });

  it("reads nothing for someone who does not prepare quotations", () => {
    scopes = ["sales.case.read"];
    renderIt();
    expect(designTextReply).not.toHaveBeenCalled();
  });
});
