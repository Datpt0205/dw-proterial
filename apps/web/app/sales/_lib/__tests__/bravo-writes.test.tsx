import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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
import { AN, orderInBravo } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];
type Write = SalesSchemas["BravoLineWriteView"];

let SCOPES = ["sales.case.read", "sales.bravo.write"];
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

let WRITES: Write[] = [];
type Targets = SalesSchemas["BravoTargetsView"];
const UAT: Targets = {
  connected: true,
  current: "uat",
  uat: true,
  production: false,
};
let TARGETS: Targets = UAT;
const api = {
  bravoWrites: vi.fn(async () => WRITES),
  bravoTargets: vi.fn(async () => TARGETS),
  proposeBravoWrite: vi.fn(async () => WRITES[0]),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import {
  BravoWritesPanel,
  CANCEL_REASON_CHARS,
  NO_SCOPE,
  OPEN_PROPOSAL,
  QUANTITY_DECIMALS,
  quantityOf,
} from "../../orders/[caseId]/bravo-writes";

function twoLines(overrides: Partial<Order> = {}): Order {
  const base = orderInBravo();
  const first = { ...base.lines[0]!, confirmed_delivery_date: "2026-12-08" };
  return {
    ...base,
    lines: [first, { ...first, line_no: 2, customer_item_code: "BRN-W-0008" }],
    ...overrides,
  };
}

function write(overrides: Partial<Write> = {}): Write {
  return {
    approval_id: "a-1",
    line_no: 1,
    field: "quantity",
    before: "6100",
    after: "6000",
    target: "uat",
    status: "proposed",
    check: null,
    reason: null,
    warnings: [],
    proposed_at: "2026-11-26T02:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

const onChanged = vi.fn();

function panel(shown: Order) {
  return render(
    <UiProvider>
      <BravoWritesPanel
        order={shown}
        viewer={{
          principalId: AN,
          hasScope: (s: string) => SCOPES.includes(s),
        }}
        onChanged={onChanged}
      />
    </UiProvider>,
  );
}

function propose(line: number): HTMLButtonElement {
  return screen.getByRole("button", {
    name: `Đề xuất ghi dòng ${line} vào Bravo`,
  }) as HTMLButtonElement;
}

async function openModal(line: number) {
  await waitFor(() => expect(propose(line).disabled).toBe(false));
  fireEvent.click(propose(line));
  return screen.findByRole("dialog");
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  SCOPES = ["sales.case.read", "sales.bravo.write"];
  WRITES = [];
  TARGETS = UAT;
});

// antd's Table and Modal take seconds to first render in jsdom.
describe(
  "Ghi vào Bravo on the order page (tickets 53, 71)",
  { timeout: 30_000 },
  () => {
    it.each([
      ["uat", "Bravo UAT"],
      ["production", "Bravo thật"],
    ] as const)(
      "tags the panel with the Bravo it reads and writes now: %s",
      async (current, shown) => {
        TARGETS = { ...UAT, current, production: true };
        panel(twoLines());
        expect(await screen.findByText(shown)).toBeTruthy();
      },
    );

    it("tags nothing when the gateway did not say which Bravo", async () => {
      TARGETS = {
        connected: false,
        current: null,
        uat: false,
        production: false,
      };
      panel(twoLines());
      await waitFor(() => expect(api.bravoTargets).toHaveBeenCalled());
      expect(screen.queryByText("Bravo UAT")).toBeNull();
      expect(screen.queryByText("Bravo thật")).toBeNull();
    });

    it("draws nothing before the order has a Bravo SO", () => {
      panel(twoLines({ bravo_so_no: null }));
      expect(screen.queryByText(/Ghi vào Bravo · SO/)).toBeNull();
      expect(api.bravoWrites).not.toHaveBeenCalled();
    });

    it("shows a reader without the write scope the history and why they cannot propose", async () => {
      SCOPES = ["sales.case.read"];
      WRITES = [write({ status: "refused" })];
      panel(twoLines());
      expect(await screen.findByText("Bravo từ chối")).toBeTruthy();
      expect(screen.getByText("Số lượng: 6.100 → 6.000")).toBeTruthy();
      expect(propose(1).disabled).toBe(true);
      expect(propose(2).disabled).toBe(true);
      expect(screen.getByText(NO_SCOPE)).toBeTruthy();
    });

    it("draws a cancel in the history as the cancel it is, with its approval", async () => {
      WRITES = [
        write({ field: "cancel", before: "6100", after: "Hủy: khách bỏ" }),
      ];
      panel(twoLines());
      expect(
        await screen.findByText("Hủy dòng: 6.100 → Hủy: khách bỏ"),
      ).toBeTruthy();
      expect(
        screen.getByRole("link", { name: "Phiếu duyệt" }).getAttribute("href"),
      ).toBe("/approvals/a-1");
    });

    // A popover opened on top of the table: the slowest render here.
    it(
      "says where the gateway stopped a write and what it answered",
      { timeout: 60_000 },
      async () => {
        WRITES = [
          write({
            status: "refused",
            check: "switch",
            reason: "write_kind_disabled",
            warnings: ["SO_W12"],
          }),
        ];
        panel(twoLines());
        expect(
          await screen.findByText("Ở bước: Loại ghi chưa bật cho đơn vị"),
        ).toBeTruthy();
        fireEvent.click(
          screen.getByRole("button", { name: "Bravo trả lời về dòng 1" }),
        );
        expect(
          await screen.findByText("Bravo trả lời: write_kind_disabled"),
        ).toBeTruthy();
        expect(screen.getByText("Cảnh báo, khác biệt: SO_W12")).toBeTruthy();
      },
    );

    // A popover opened on top of the table: the slowest render here.
    it(
      "shows what a write with differences wrote differently",
      { timeout: 60_000 },
      async () => {
        WRITES = [
          write({
            status: "written_with_differences",
            check: "write",
            warnings: ["Quantity9"],
          }),
        ];
        panel(twoLines());
        await screen.findByText("Đã ghi, Bravo lưu khác");
        // It was written: no "stopped at" for it.
        expect(screen.queryByText(/Ở bước/)).toBeNull();
        fireEvent.click(
          screen.getByRole("button", { name: "Bravo trả lời về dòng 1" }),
        );
        expect(
          await screen.findByText("Cảnh báo, khác biệt: Quantity9"),
        ).toBeTruthy();
      },
    );

    it("offers one proposal per line while the line's last one waits", async () => {
      WRITES = [write({ status: "proposed" })];
      panel(twoLines());
      await screen.findByText("Đề xuất, chờ duyệt");
      expect(propose(1).disabled).toBe(true);
      expect(screen.getByText(OPEN_PROPOSAL)).toBeTruthy();
      expect(propose(2).disabled).toBe(false);
    });

    it("proposes a cancel with its reason, trimmed", async () => {
      panel(twoLines());
      const dialog = await openModal(2);
      fireEvent.click(within(dialog).getByText("Hủy dòng"));
      const reason = await within(dialog).findByLabelText("Lý do hủy");
      expect(reason.getAttribute("maxlength")).toBe(
        String(CANCEL_REASON_CHARS),
      );
      fireEvent.change(reason, { target: { value: "  khách bỏ dòng  " } });
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Đề xuất hủy dòng" }),
      );
      await waitFor(() =>
        expect(api.proposeBravoWrite).toHaveBeenCalledWith(
          twoLines().case_id,
          2,
          {
            case_version: 7,
            change: { field: "cancel", reason: "khách bỏ dòng" },
          },
          expect.any(String),
        ),
      );
    });

    it("refuses a cancel without its reason before anything is sent", async () => {
      panel(twoLines());
      const dialog = await openModal(1);
      fireEvent.click(within(dialog).getByText("Hủy dòng"));
      const reason = await within(dialog).findByLabelText("Lý do hủy");
      fireEvent.change(reason, { target: { value: "   " } });
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Đề xuất hủy dòng" }),
      );
      expect(await within(dialog).findByText("Ghi lý do hủy")).toBeTruthy();
      expect(api.proposeBravoWrite).not.toHaveBeenCalled();
    });

    it("sends the confirmed date as a calendar day", async () => {
      panel(twoLines());
      const dialog = await openModal(1);
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Gửi đề xuất" }),
      );
      await waitFor(() =>
        expect(api.proposeBravoWrite).toHaveBeenCalledWith(
          twoLines().case_id,
          1,
          {
            case_version: 7,
            change: { field: "confirmed_date", value: "2026-12-08" },
          },
          expect.any(String),
        ),
      );
    });

    it("reads a quantity with the Vietnamese comma and sends it as a string", async () => {
      panel(twoLines());
      const dialog = await openModal(1);
      fireEvent.click(within(dialog).getByText("Số lượng"));
      const quantity = await within(dialog).findByLabelText(/Số lượng mới/);
      fireEvent.change(quantity, { target: { value: "1.200,5" } });
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Gửi đề xuất" }),
      );
      await waitFor(() =>
        expect(api.proposeBravoWrite).toHaveBeenCalledWith(
          twoLines().case_id,
          1,
          { case_version: 7, change: { field: "quantity", value: "1200.5" } },
          expect.any(String),
        ),
      );
    });

    it("keeps what was typed and reloads the order when the case changed", async () => {
      api.proposeBravoWrite.mockRejectedValueOnce(
        new ApiError(409, {
          code: "conflict",
          message: "Hồ sơ đã thay đổi kể từ khi bạn mở: tải lại rồi làm lại.",
          details: { rule: "stale_case_version" },
          request_id: "req-1",
        }),
      );
      panel(twoLines());
      const dialog = await openModal(1);
      fireEvent.click(within(dialog).getByText("Hủy dòng"));
      const reason = await within(dialog).findByLabelText("Lý do hủy");
      fireEvent.change(reason, { target: { value: "khách bỏ" } });
      fireEvent.click(
        within(dialog).getByRole("button", { name: "Đề xuất hủy dòng" }),
      );
      expect(
        await within(dialog).findByText(/Hồ sơ đã thay đổi kể từ khi bạn mở/),
      ).toBeTruthy();
      expect((reason as HTMLInputElement).value).toBe("khách bỏ");
      expect(onChanged).toHaveBeenCalledTimes(1);
    });
  },
);

describe("the form's limits are the contract's", () => {
  const spec = JSON.parse(
    readFileSync(
      resolve(__dirname, "../../../../../../contracts/openapi/openapi.json"),
      "utf8",
    ),
  ) as {
    components: {
      schemas: Record<
        string,
        { properties: Record<string, Record<string, unknown>> }
      >;
    };
  };
  const schemas = spec.components.schemas;

  it("caps a cancel's reason where the server does", () => {
    expect(schemas.CancelChange!.properties.reason!.maxLength).toBe(
      CANCEL_REASON_CHARS,
    );
  });

  it("sends only a quantity the server's pattern takes", () => {
    const anyOf = schemas.QuantityChange!.properties.value!.anyOf as {
      pattern?: string;
    }[];
    const pattern = new RegExp(anyOf.find((s) => s.pattern)!.pattern!);
    for (const typed of ["1.200", "1200,5", "0,2500", "6100"]) {
      const sent = quantityOf(typed);
      expect(sent, typed).not.toBeNull();
      expect(pattern.test(sent!), typed).toBe(true);
    }
    for (const typed of ["0", "-5", "1,23456", "abc"]) {
      expect(quantityOf(typed), typed).toBeNull();
    }
    // The pattern is not anchored, so the decimals are read from its text.
    expect(anyOf.find((s) => s.pattern)!.pattern).toContain(
      String.raw`\.\d{0,${QUANTITY_DECIMALS}}`,
    );
  });
});
