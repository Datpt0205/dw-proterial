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
import { HandoffDraft } from "../../inbox/handoff-draft";

type Draft = NonNullable<SalesSchemas["InboxMessageView"]["handoff_draft"]>;
type Handoff = NonNullable<SalesSchemas["MessageDispositionView"]["handoff"]>;

const QUOTE = "có 2 cuộn bị móp lõi cuộn";

function handoff(overrides: Partial<Handoff> = {}): Handoff {
  return {
    kind: "complaint",
    prompt: "sales.request_handoff@1.0.0",
    model_profile: "onprem",
    route: "structured_extraction",
    rules: "sales_order_rules@1.4.1",
    outcome: "read",
    po_no: "VLX-PO-2608-0102",
    po: { text: "VLX-PO-2608-0102", start: 40, end: 56 },
    so_no: "SO26-0812",
    order_case_id: null,
    lines: [],
    lot: { text: "LOT-2609-118", start: 120, end: 132 },
    quotes: [{ text: QUOTE, start: 80, end: 105 }],
    sample_quantity: null,
    quantity: null,
    refused: {},
    ...overrides,
  };
}

const DRAFT: Draft = {
  to: "qa",
  subject:
    "[Chuyển QA] Khách VLX phản ánh chất lượng – PO VLX-PO-2608-0102, lô LOT-2609-118",
  body: `Chào anh/chị QA,\n\nKhách VLX viết:\n  «${QUOTE}»\n\nSales`,
  template_ref: "sales_handoffs@1.0.0#complaint",
};

afterEach(() => cleanup());

function shown(h: Handoff) {
  return render(
    <UiProvider>
      <HandoffDraft draft={DRAFT} handoff={h} />
    </UiProvider>,
  );
}

describe("a hand-off DW1 pre-filled from a routed mail (ticket 33)", () => {
  it("says a model copied it, keeps it editable and copies what Sales edited", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    shown(handoff());

    expect(
      screen.getByText("Mô hình chép từ thư khách, DW1 kiểm từng giá trị"),
    ).toBeTruthy();
    expect(
      screen.getByText(/PO VLX-PO-2608-0102 · đơn bán SO26-0812/),
    ).toBeTruthy();
    const body = screen.getByLabelText("Nội dung") as HTMLTextAreaElement;
    expect(body.value).toContain(`«${QUOTE}»`);
    fireEvent.change(body, { target: { value: "Đã sửa" } });
    fireEvent.click(screen.getByRole("button", { name: "Chép bản chuyển" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(`${DRAFT.subject}\n\nĐã sửa`);
  });

  it("an answer code kept nothing of is an empty form, said as such", () => {
    shown(
      handoff({
        outcome: "unavailable",
        po_no: null,
        po: null,
        so_no: null,
        lot: null,
        quotes: [],
      }),
    );

    expect(
      screen.getByText("Mô hình không đọc được: điền tay như trước"),
    ).toBeTruthy();
    expect(
      screen.getByText("Mọi giá trị đang để “chưa rõ”: đọc thư khách và điền."),
    ).toBeTruthy();
  });
});
