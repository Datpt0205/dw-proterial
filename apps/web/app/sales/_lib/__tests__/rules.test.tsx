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
import { AN, GIANG } from "./fixtures";
import {
  keyRows,
  nextVersion,
  parseDocument,
  startOptions,
  type PlatformDocument,
  type RuleVersion,
} from "../rules";

type View = SalesSchemas["RulesInForceView"];

const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../../../contracts/jsonschema/sales_rules.json",
    ),
    "utf-8",
  ),
) as Record<string, Record<string, unknown>>;

let scopes = ["sales.case.read", "sales.rules.propose"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

function kpi(version: string, hours: number) {
  return {
    schema_version: "1.0",
    policy_id: "sales_kpi",
    policy_version: version,
    order_confirmation_target_hours: hours,
    quotation_target_days: 1,
    manual_baseline_minutes: { O1: 5, Q1: 10 },
  };
}

const KPI_DOC = kpi("1.0.1", 8);

function version(overrides: Partial<RuleVersion>): RuleVersion {
  return {
    version_id: "0aa10aa0-c939-7000-8539-31fd3e621700",
    key: "sales_kpi",
    version: "1.0.1",
    ref: "sales_kpi@1.0.1",
    layer: "tenant",
    status: "approved",
    proposed_by: AN,
    proposed_at: "2026-10-10T02:00:00Z",
    decided_by: GIANG,
    decided_at: "2026-10-10T03:00:00Z",
    comment: null,
    document: KPI_DOC,
    approval_id: "0aa10aa0-c939-7000-8539-31fd3e621701",
    ...overrides,
  };
}

const WAITING = version({
  version_id: "0aa10aa0-c939-7000-8539-31fd3e621702",
  key: "sales_order_rules",
  version: "1.5.2",
  ref: "sales_order_rules@1.5.2",
  status: "proposed",
  proposed_at: "2026-10-14T02:00:00Z",
  decided_by: null,
  decided_at: null,
  document: { id: "sales_order_rules", version: "1.5.2" },
  approval_id: "0aa10aa0-c939-7000-8539-31fd3e621703",
});

// A KPI version the head turned down, which a person may start again from.
const REJECTED = version({
  version_id: "0aa10aa0-c939-7000-8539-31fd3e621704",
  version: "1.0.3",
  ref: "sales_kpi@1.0.3",
  status: "rejected",
  proposed_at: "2026-10-12T02:00:00Z",
  document: kpi("1.0.3", 4),
  approval_id: "0aa10aa0-c939-7000-8539-31fd3e621705",
});

const VIEW: View = {
  in_force: {
    sales_order_rules: "sales_order_rules@1.5.1",
    sales_kpi: "sales_kpi@1.0.1",
  },
  layers: { sales_order_rules: "platform", sales_kpi: "tenant" },
  platform: [
    { key: "sales_order_rules", ref: "sales_order_rules@1.5.1" },
    { key: "sales_kpi", ref: "sales_kpi@1.0.0" },
  ],
  versions: [version({}), WAITING, REJECTED],
};

const PLATFORM_KPI: PlatformDocument[] = [
  {
    key: "sales_kpi",
    ref: "sales_kpi@1.0.0",
    version: "1.0.0",
    current: true,
    document: kpi("1.0.0", 12),
  },
];

const api = {
  rules: vi.fn(async () => VIEW),
  proposeRule: vi.fn(async (...args: unknown[]) => (void args, WAITING)),
  ruleSchema: vi.fn(async (key: string) => ({
    key,
    json_schema: SCHEMAS[key]!,
  })),
  rulePlatformDocuments: vi.fn(async () => PLATFORM_KPI),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import RulesPage from "../../rules/page";

const SLOW = 30_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.case.read", "sales.rules.propose"];
});

function renderPage() {
  render(
    <UiProvider>
      <RulesPage />
    </UiProvider>,
  );
}

async function openKpi() {
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
    }),
  );
  return (await screen.findByRole("spinbutton", {
    name: "Mục tiêu xác nhận đơn hàng",
  })) as HTMLInputElement;
}

describe("the rules list's logic (tickets 38, 40)", () => {
  it("gives each key what applies, its layer, the platform's and how many wait", () => {
    expect(keyRows(VIEW)).toEqual([
      {
        key: "sales_order_rules",
        inForce: "sales_order_rules@1.5.1",
        layer: "platform",
        platform: "sales_order_rules@1.5.1",
        waiting: 1,
      },
      {
        key: "sales_kpi",
        inForce: "sales_kpi@1.0.1",
        layer: "tenant",
        platform: "sales_kpi@1.0.0",
        waiting: 0,
      },
    ]);
  });

  it("offers what applies first, then the company's versions, then the platform's", () => {
    const options = startOptions(VIEW, "sales_kpi", PLATFORM_KPI);
    expect(options.map((o) => [o.ref, o.layer, o.inForce])).toEqual([
      ["sales_kpi@1.0.1", "tenant", true],
      ["sales_kpi@1.0.3", "tenant", false],
      ["sales_kpi@1.0.0", "platform", false],
    ]);
    // Where the platform's applies, its version is the one in force.
    const orders = startOptions(VIEW, "sales_order_rules", [
      {
        ...PLATFORM_KPI[0]!,
        key: "sales_order_rules",
        ref: "sales_order_rules@1.5.1",
      },
    ]);
    expect(orders[0]).toMatchObject({
      ref: "sales_order_rules@1.5.1",
      inForce: true,
    });
  });

  it("offers one patch above every number the key has used", () => {
    expect(
      nextVersion(["sales_kpi@1.0.1", "sales_kpi@1.0.3", "sales_kpi@1.0.0"]),
    ).toBe("1.0.4");
    expect(nextVersion(["k@1.10.0", "k@1.9.9"])).toBe("1.10.1");
    expect(nextVersion([])).toBe("0.0.1");
  });

  it("takes one JSON object as a document and refuses anything else in words", () => {
    expect(parseDocument('{"id": "sales_kpi"}')).toEqual({
      ok: true,
      document: { id: "sales_kpi" },
    });
    for (const text of ["", "{", "[]", "null", "3"])
      expect(parseDocument(text).ok, text).toBe(false);
  });
});

describe("the rules page (tickets 38, 40)", () => {
  it(
    "lists what applies per key and every version, each linked to its approval",
    async () => {
      renderPage();
      const kpiRow = (await screen.findByText("sales_kpi@1.0.0")).closest(
        "tr",
      )!;
      expect(within(kpiRow).getByText("Riêng của công ty")).toBeTruthy();
      const [inForce, shipped] = screen.getAllByText("sales_order_rules@1.5.1");
      const orders = inForce!.closest("tr")!;
      expect(shipped!.closest("tr")).toBe(orders);
      expect(within(orders).getByText("Của nền tảng")).toBeTruthy();

      const waiting = screen
        .getByText("sales_order_rules@1.5.2")
        .closest("tr")!;
      expect(within(waiting).getByText("Chờ duyệt")).toBeTruthy();
      expect(
        within(waiting)
          .getByRole("link", { name: "Mở yêu cầu duyệt" })
          .getAttribute("href"),
      ).toBe(`/approvals/${WAITING.approval_id}`);
      expect(screen.queryByRole("button", { name: /^Duyệt/ })).toBeNull();
    },
    SLOW,
  );

  it(
    "edits a key in a form from its schema, shows the changes, then proposes with a key minted for the press",
    async () => {
      renderPage();
      const hours = await openKpi();
      // The version in force, under the next free number.
      expect(hours.value).toBe("8");
      expect(
        (
          screen.getByRole("textbox", {
            name: "Số phiên bản mới",
          }) as HTMLInputElement
        ).value,
      ).toBe("1.0.4");
      expect(api.ruleSchema).toHaveBeenCalledWith("sales_kpi");

      fireEvent.change(hours, { target: { value: "6" } });
      fireEvent.blur(hours);
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));

      expect(
        await screen.findByText("2 thay đổi so với sales_kpi@1.0.1."),
      ).toBeTruthy();
      const row = screen
        .getByText("Mục tiêu xác nhận đơn hàng", { selector: "strong" })
        .closest("tr")!;
      expect(within(row).getByText("Đổi")).toBeTruthy();
      expect(within(row).getByText("8")).toBeTruthy();
      expect(within(row).getByText("6")).toBeTruthy();
      expect(api.proposeRule).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      await waitFor(() => expect(api.proposeRule).toHaveBeenCalledTimes(1));
      const [key, body, idempotency] = api.proposeRule.mock.calls[0] as [
        string,
        unknown,
        string,
      ];
      expect([key, body]).toEqual([
        "sales_kpi",
        {
          document: {
            ...KPI_DOC,
            policy_version: "1.0.4",
            order_confirmation_target_hours: 6,
          },
        },
      ]);
      expect(idempotency).toMatch(/^[0-9a-f-]{36}$/);
      await waitFor(() => expect(api.rules).toHaveBeenCalledTimes(2));
    },
    SLOW,
  );

  it(
    "puts the server's refusal on the field it names, and the rest in the summary",
    async () => {
      api.proposeRule.mockRejectedValueOnce(
        new ApiError(422, {
          code: "validation_failed",
          message: "the document is not a valid version of this key",
          details: {
            key: "sales_kpi",
            errors: "['order_confirmation_target_hours', '']",
          },
          request_id: "r-1",
        }),
      );
      renderPage();
      await openKpi();
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      fireEvent.click(await screen.findByRole("button", { name: "Gửi duyệt" }));

      expect(await screen.findByText("Còn 2 trường cần sửa.")).toBeTruthy();
      expect(
        screen.getByText(/^Toàn bộ tài liệu: Máy chủ không nhận/),
      ).toBeTruthy();
      const hours = screen.getByRole("spinbutton", {
        name: "Mục tiêu xác nhận đơn hàng",
      });
      const item = hours.closest(".ant-form-item")!;
      expect(
        within(item as HTMLElement).getByText(/Máy chủ không nhận giá trị này/),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "starts from an earlier version: Dùng lại phiên bản này prefills it as a new proposal",
    async () => {
      renderPage();
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Dùng lại phiên bản này: sales_kpi@1.0.3",
        }),
      );
      const hours = (await screen.findByRole("spinbutton", {
        name: "Mục tiêu xác nhận đơn hàng",
      })) as HTMLInputElement;
      expect(hours.value).toBe("4");
      expect(
        (
          screen.getByRole("textbox", {
            name: "Số phiên bản mới",
          }) as HTMLInputElement
        ).value,
      ).toBe("1.0.4");
      // Compared with what applies, not with the version it started from.
      fireEvent.click(screen.getByRole("button", { name: "Xem thay đổi" }));
      expect(
        await screen.findByText("2 thay đổi so với sales_kpi@1.0.1."),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "keeps a JSON editor for experts, and brings its edits back to the form",
    async () => {
      renderPage();
      await openKpi();
      fireEvent.click(screen.getByText("JSON nâng cao"));
      const editor = (await screen.findByRole("textbox", {
        name: "Tài liệu (JSON)",
      })) as HTMLTextAreaElement;
      const document = JSON.parse(editor.value) as Record<string, unknown>;
      expect(document.order_confirmation_target_hours).toBe(8);
      fireEvent.change(editor, {
        target: {
          value: JSON.stringify({
            ...document,
            order_confirmation_target_hours: 7,
          }),
        },
      });
      fireEvent.click(screen.getByText("Biểu mẫu"));
      await waitFor(
        () =>
          expect(
            (
              screen.getByRole("spinbutton", {
                name: "Mục tiêu xác nhận đơn hàng",
              }) as HTMLInputElement
            ).value,
          ).toBe("7"),
        // The form remounts with the JSON's values: slow under a loaded runner.
        { timeout: 10_000 },
      );
      // Text that is not JSON stays in the JSON editor, said in words.
      fireEvent.click(screen.getByText("JSON nâng cao"));
      const jsonBox = () =>
        screen.getByRole("textbox", {
          name: "Tài liệu (JSON)",
        }) as HTMLTextAreaElement;
      // Type only once the editor shows the document the form holds, as a
      // person would: under a loaded runner the switch settles a moment after
      // the click, and text typed before it was overwritten.
      await waitFor(
        () =>
          expect(jsonBox().value).toContain(
            '"order_confirmation_target_hours": 7',
          ),
        { timeout: 10_000 },
      );
      fireEvent.change(jsonBox(), { target: { value: "{ not json" } });
      await waitFor(() => expect(jsonBox().value).toBe("{ not json"));
      fireEvent.click(screen.getByText("Biểu mẫu"));
      expect(
        await screen.findByText(/Tài liệu phải là JSON hợp lệ/, undefined, {
          timeout: 10_000,
        }),
      ).toBeTruthy();
      expect(
        screen.getByRole("textbox", { name: "Tài liệu (JSON)" }),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "asks before closing an edited document, and keeps it on Tiếp tục sửa",
    async () => {
      renderPage();
      const hours = await openKpi();
      fireEvent.change(hours, { target: { value: "9" } });

      fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
      expect(
        (await screen.findAllByText("Bỏ tài liệu đang sửa?")).length,
      ).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole("button", { name: "Tiếp tục sửa" }));
      expect(
        (
          screen.getByRole("spinbutton", {
            name: "Mục tiêu xác nhận đơn hàng",
          }) as HTMLInputElement
        ).value,
      ).toBe("9");

      fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
      const discard = await screen.findAllByRole("button", {
        name: "Bỏ thay đổi",
      });
      fireEvent.click(discard[discard.length - 1]!);
      await waitFor(() =>
        expect(
          screen.queryByRole("spinbutton", {
            name: "Mục tiêu xác nhận đơn hàng",
          }),
        ).toBeNull(),
      );
      expect(api.proposeRule).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it("draws the forbidden state, and asks nothing, without sales.rules.propose", () => {
    scopes = ["sales.case.read"];
    renderPage();
    expect(
      screen.getByText(/Quyền của bạn trong không gian làm việc này/),
    ).toBeTruthy();
    expect(api.rules).not.toHaveBeenCalled();
  });
});
