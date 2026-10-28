import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";

type Quote = SalesSchemas["QuoteCaseView"];
type Artifact = SalesSchemas["ArtifactView"];

let scopes = ["sales.case.read", "sales.quote.prepare", "sales.price.read"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: "u-an",
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../people", () => ({
  usePeople: () => (id: string) => `Người ${id}`,
}));
const api = {
  uploadSignedQuote: vi.fn(async () => ({})),
  downloadArtifact: vi.fn(async () => new Blob(["%PDF-"])),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { SendPanel } from "../../quotes/[caseId]/send-panel";

function artifact(kind: string, contentType: string, id: string): Artifact {
  return {
    artifact_id: id,
    kind,
    case_version: 9,
    template_ref: "quote@1.0.0",
    sha256: "a".repeat(64),
    content_type: contentType,
    size_bytes: 10,
    file_name: `${kind}.bin`,
    created_by: "u-an",
    created_at: "2026-10-28T03:00:00Z",
    downloadable: true,
  } as Artifact;
}

const FINALS = [
  artifact("quotation_final", "application/pdf", "a-pdf"),
  artifact(
    "quotation_final",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "a-xlsx",
  ),
];

function quote(extra: Partial<Quote> = {}): Quote {
  return {
    case_id: "q-1",
    case_version: 9,
    status: "approved",
    signed_copy: null,
    ...extra,
  } as Quote;
}

function panel(q: Quote, artifacts: Artifact[] = FINALS) {
  return render(
    <UiProvider>
      <SendPanel quote={q} artifacts={artifacts} onChanged={() => undefined} />
    </UiProvider>,
  );
}

function choose(file: File) {
  const input = document.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.case.read", "sales.quote.prepare", "sales.price.read"];
});

describe("an approved quotation, sent without an e-signature (2026-10-28)", () => {
  it("offers the final document to download and to print, and says no e-signature", () => {
    panel(quote());
    expect(screen.getByRole("button", { name: /Tải PDF/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Tải Excel/ })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Mở bản PDF để in/ }),
    ).toBeTruthy();
    expect(screen.getByText(/không dùng chữ ký điện tử/)).toBeTruthy();
  });

  it("uploads the signed scan as base64 at the case version", async () => {
    panel(quote());
    choose(
      new File(["%PDF-1.4 signed"], "da-ky.pdf", { type: "application/pdf" }),
    );
    await waitFor(() => expect(api.uploadSignedQuote).toHaveBeenCalledTimes(1));
    const [caseId, version, content] = api.uploadSignedQuote.mock
      .calls[0] as unknown as [string, number, string];
    expect([caseId, version]).toEqual(["q-1", 9]);
    expect(atob(content)).toBe("%PDF-1.4 signed");
  });

  it("refuses a file over 10 MB before sending it", async () => {
    panel(quote());
    const big = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    choose(big);
    expect(
      await screen.findByText("Bản đã ký phải nhỏ hơn 10 MB."),
    ).toBeTruthy();
    expect(api.uploadSignedQuote).not.toHaveBeenCalled();
  });

  it("says why someone without the price scope cannot upload it", () => {
    scopes = ["sales.case.read", "sales.quote.prepare"];
    panel(quote());
    const button = screen.getByRole("button", { name: /Tải lên bản đã ký/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText(
        "Tải lên bản đã ký cần vai Sales phụ trách và quyền xem giá.",
      ),
    ).toBeTruthy();
  });

  it("shows the signed copy kept with the case, after it was sent too", () => {
    panel(
      quote({
        status: "sent",
        signed_copy: {
          artifact_id: "a-signed",
          content_type: "application/pdf",
          uploaded_by: "u-an",
          uploaded_at: "2026-10-28T04:00:00Z",
        },
      }),
      [...FINALS, artifact("quote_signed", "application/pdf", "a-signed")],
    );
    expect(screen.getByText(/Đã tải lên: Người u-an/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Tải bản đã ký/ })).toBeTruthy();
    expect(screen.queryByText(/3\. Gửi khách/)).toBeNull();
  });
});
