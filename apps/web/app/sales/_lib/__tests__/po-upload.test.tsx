import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));

const uploadPo = vi.fn();
const customers = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ uploadPo, customers }),
}));

import { PoUpload } from "../../inbox/po-upload";

afterEach(() => {
  cleanup();
  uploadPo.mockReset();
  customers.mockReset();
});

function renderIt(reason: string | null = null) {
  customers.mockResolvedValue({
    items: [{ code: "CVG", name: "Corvane Group Japan Ltd." }],
  });
  const onUploaded = vi.fn();
  render(
    <UiProvider>
      <PoUpload reason={reason} onUploaded={onUploaded} />
    </UiProvider>,
  );
  return onUploaded;
}

async function chooseCustomerAndFile() {
  fireEvent.click(screen.getByRole("button", { name: /Tải PO lên/ }));
  const dialog = await screen.findByRole("dialog");
  const select = within(dialog).getByRole("combobox", { name: "Khách hàng" });
  fireEvent.mouseDown(select);
  fireEvent.click(await screen.findByText("CVG · Corvane Group Japan Ltd."));
  const input = dialog.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["PO"], "ORD_20261111.csv", { type: "text/csv" });
  fireEvent.change(input, { target: { files: [file] } });
  await within(dialog).findByText("ORD_20261111.csv");
  return dialog;
}

describe("Tải PO lên (ticket 18)", () => {
  it("is refused with its reason when the person may not process the mailbox", () => {
    renderIt("Bạn không có quyền cho DW1 xử lý thư.");
    expect(
      (
        screen.getByRole("button", {
          name: /Tải PO lên/,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("sends the chosen customer and the file, never who uploads", async () => {
    uploadPo.mockResolvedValue({
      message_id: "upload-abc",
      customer_code: "CVG",
      already_stored: false,
      job: null,
    });
    const onUploaded = renderIt();
    const dialog = await chooseCustomerAndFile();
    fireEvent.click(within(dialog).getByRole("button", { name: "Tải lên" }));
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalled());
    const [body] = uploadPo.mock.calls[0]!;
    expect(Object.keys(body).sort()).toEqual(["customer_code", "files"]);
    expect(body.customer_code).toBe("CVG");
    expect(body.files).toEqual([
      { file_name: "ORD_20261111.csv", content_b64: "UE8=" },
    ]);
  });

  it("says when the file was uploaded before, and closes nothing", async () => {
    uploadPo.mockResolvedValue({
      message_id: "upload-abc",
      customer_code: "CVG",
      already_stored: true,
      job: null,
    });
    const onUploaded = renderIt();
    const dialog = await chooseCustomerAndFile();
    fireEvent.click(within(dialog).getByRole("button", { name: "Tải lên" }));
    expect(
      await within(dialog).findByText(/đã được tải lên trước đó/),
    ).toBeTruthy();
    expect(onUploaded).not.toHaveBeenCalled();
  });
});
