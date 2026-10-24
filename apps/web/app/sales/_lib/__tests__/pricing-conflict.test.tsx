import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { DIEU, GIANG, pendingQuote } from "./fixtures";

/**
 * Two people price one quote at once (defect E, 2026-10-21): the second is
 * refused for a stale version and sees the price the first one saved beside
 * the one they typed, which stays in the form, and chooses which stands
 * (ui-quality §4 "conflict"). Never a silent overwrite.
 */
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: GIANG,
    displayName: "Giang",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

type Quote = SalesSchemas["QuoteCaseView"];

/** M10 at "Design đã trả lời": one line, nothing priced yet, version 6. */
function designReplied(): Quote {
  return {
    ...pendingQuote(),
    status: "design_replied",
    case_version: 6,
    lines: [
      {
        line_no: 1,
        customer_item_code: null,
        description: "Cáp 2C AWG24 BLK",
        quantity: "3000",
        uom: "m",
        target_price: null,
        needed_by: null,
        anchors: {},
        model_read: [],
        candidates: [],
      },
    ],
    pricing: null,
    submission: null,
    decision: null,
  };
}

/** What Diệu saved first: 0.6890 on version 7. */
function pricedByDieu(): Quote {
  return {
    ...designReplied(),
    status: "priced",
    case_version: 7,
    pricing: {
      decided_by: DIEU,
      decided_at: "2026-10-05T04:00:00Z",
      lines: [
        {
          line_no: 1,
          unit_price: "0.6890",
          moq: "3000",
          lead_time_days: 45,
          copper_basis: { kind: "fixed" },
        },
      ],
      lme: null,
      management_guidance: null,
    },
  };
}

const stale = () =>
  new ApiError(409, {
    code: "conflict",
    message: "Hồ sơ đã thay đổi kể từ khi bạn mở: tải lại rồi làm lại.",
    details: { rule: "stale_case_version" },
    request_id: "req-1",
  });

const api = {
  lme: vi.fn(async () => ({ items: [] })),
  price: vi.fn(),
  quote: vi.fn(async () => pricedByDieu()),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { PricingForm } from "../../quotes/[caseId]/pricing";

const onDone = vi.fn();

function form() {
  return render(
    <UiProvider>
      <PricingForm quote={designReplied()} onDone={onDone} />
    </UiProvider>,
  );
}

async function typeAndRecord() {
  fireEvent.change(await screen.findByLabelText("Đơn giá dòng 1"), {
    target: { value: "0,74" },
  });
  fireEvent.change(screen.getByLabelText("MOQ dòng 1"), {
    target: { value: "3000" },
  });
  fireEvent.change(screen.getByLabelText("Lead time dòng 1"), {
    target: { value: "45" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ghi giá" }));
}

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a pricing conflict (defect E)", () => {
  it(
    "shows the saved price beside the typed one, and keeps what was typed",
    async () => {
      api.price.mockRejectedValueOnce(stale());
      form();
      await typeAndRecord();

      const alert = await screen.findByRole("alert");
      await waitFor(() =>
        expect(alert.textContent).toContain("Người khác vừa ghi giá"),
      );
      expect(alert.textContent).toContain("0,689");
      expect(alert.textContent).toMatch(/bạn đang nhập: 0,74/);
      expect(alert.textContent).toContain("Hồ sơ đã thay đổi");
      // The typed price is still in the field, not replaced by the saved one.
      expect(
        (screen.getByLabelText("Đơn giá dòng 1") as HTMLInputElement).value,
      ).toBe("0,74");
      expect(api.quote).toHaveBeenCalledTimes(1);
      expect(onDone).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "'Dùng giá của tôi' records the typed price again on the saved version",
    async () => {
      api.price.mockRejectedValueOnce(stale());
      api.price.mockResolvedValueOnce({ case_version: 8 });
      form();
      await typeAndRecord();

      const alert = await screen.findByRole("alert");
      fireEvent.click(
        await within(alert).findByRole("button", { name: "Dùng giá của tôi" }),
      );
      await waitFor(() => expect(api.price).toHaveBeenCalledTimes(2));
      const [first, second] = api.price.mock.calls.map(
        (call) => call[1] as { case_version: number; lines: unknown[] },
      );
      expect(first!.case_version).toBe(6);
      expect(second!.case_version).toBe(7);
      expect(second!.lines).toEqual([
        expect.objectContaining({ unit_price: "0.74", moq: "3000" }),
      ]);
      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
      expect(screen.queryByText(/Người khác vừa ghi giá/)).toBeNull();
    },
    SLOW,
  );

  it(
    "'Giữ giá hiện có' takes the saved price into the form and records nothing",
    async () => {
      api.price.mockRejectedValueOnce(stale());
      form();
      await typeAndRecord();

      const alert = await screen.findByRole("alert");
      fireEvent.click(
        await within(alert).findByRole("button", { name: "Giữ giá hiện có" }),
      );
      await waitFor(() =>
        expect(
          (screen.getByLabelText("Đơn giá dòng 1") as HTMLInputElement).value,
        ).toMatch(/^0,689/),
      );
      expect(api.price).toHaveBeenCalledTimes(1);
      expect(onDone).toHaveBeenCalledTimes(1);
      expect(screen.queryByText(/Người khác vừa ghi giá/)).toBeNull();
    },
    SLOW,
  );

  it(
    "another refusal is drawn as before, without reading the case again",
    async () => {
      api.price.mockRejectedValueOnce(
        new ApiError(409, {
          code: "conflict",
          message: "Chọn tháng LME.",
          details: { latest_month: "2026-09" },
          request_id: "req-2",
        }),
      );
      form();
      await typeAndRecord();
      expect(await screen.findByText("Chưa làm được bước này")).toBeTruthy();
      expect(api.quote).not.toHaveBeenCalled();
    },
    SLOW,
  );
});
