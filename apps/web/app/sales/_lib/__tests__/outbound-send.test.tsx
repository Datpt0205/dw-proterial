import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Artifact } from "@dw/api-client";
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

const outbound = vi.fn();
const sendArtifact = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ outbound, sendArtifact }) }));

import { OutboundSend } from "../../_components/outbound-send";

const DRAFT = {
  artifact_id: "a-1",
  kind: "send_draft",
  case_version: 7,
  downloadable: true,
} as unknown as Artifact;

afterEach(() => {
  cleanup();
  outbound.mockReset();
  sendArtifact.mockReset();
  scopes = ["sales.case.read", "sales.quote.prepare"];
});

function renderIt(draft: Artifact | undefined = DRAFT) {
  render(
    <UiProvider>
      <OutboundSend kind="quote" caseId="c-1" draft={draft} />
    </UiProvider>,
  );
}

const BUTTON = { name: /Gửi cho khách từ hộp thư của bạn/ };

describe("Gửi cho khách (2026-10-29)", () => {
  it("sends the draft from the viewer's mailbox only after they confirm", async () => {
    outbound.mockResolvedValue({ enabled: true, mails: [] });
    sendArtifact.mockResolvedValue({ mail_id: "m-1", status: "queued" });
    renderIt();
    fireEvent.click(await screen.findByRole("button", BUTTON));
    expect(sendArtifact).not.toHaveBeenCalled();
    fireEvent.click(
      await screen.findByRole("button", { name: "Gửi cho khách" }),
    );
    await waitFor(() =>
      expect(sendArtifact).toHaveBeenCalledWith(
        "quote",
        "c-1",
        "a-1",
        7,
        expect.any(String),
      ),
    );
  });

  it("says the deployment sends no mail yet, and keeps the button off", async () => {
    outbound.mockResolvedValue({ enabled: false, mails: [] });
    renderIt();
    const button = await screen.findByRole("button", BUTTON);
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(await screen.findByText(/chưa được nối để gửi thư/)).toBeTruthy();
  });

  it("says why a mail did not go, and lets it be sent again", async () => {
    outbound.mockResolvedValue({
      enabled: true,
      mails: [
        {
          mail_id: "m-1",
          artifact_id: "a-1",
          mailbox: "an.nguyen@alpha.local",
          status: "failed",
          error: "not_connected",
          queued_at: "2026-10-29T03:00:00Z",
          settled_at: "2026-10-29T03:01:00Z",
        },
      ],
    });
    renderIt();
    expect(
      await screen.findByText(/hộp thư của bạn chưa được nối/),
    ).toBeTruthy();
    const button = await screen.findByRole("button", BUTTON);
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });
});
