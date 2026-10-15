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
import type { SalesSchemas } from "@dw/api-client";
import { AN, GIANG } from "./fixtures";
import {
  keyRows,
  parseDocument,
  startingDocument,
  type RuleVersion,
} from "../rules";

type View = SalesSchemas["RulesInForceView"];

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

const KPI_DOC = { id: "sales_kpi", version: "1.0.1", target: 0.9 };

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
  versions: [version({}), WAITING],
};

const api = {
  rules: vi.fn(async () => VIEW),
  proposeRule: vi.fn(async () => WAITING),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import RulesPage from "../../rules/page";

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.case.read", "sales.rules.propose"];
});

describe("the rules list's logic (ticket 38)", () => {
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

  it("starts a proposal from the company's version in force, else its latest, else nothing", () => {
    expect(startingDocument(VIEW, "sales_kpi")).toEqual({
      document: KPI_DOC,
      inForce: true,
    });
    expect(startingDocument(VIEW, "sales_order_rules")).toEqual({
      document: WAITING.document,
      inForce: false,
    });
    expect(startingDocument(VIEW, "sales_pricing")).toBeNull();
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

describe("the rules page (ticket 38)", () => {
  it(
    "lists what applies per key and every version, each linked to its approval",
    async () => {
      render(
        <UiProvider>
          <RulesPage />
        </UiProvider>,
      );

      const kpi = (await screen.findByText("sales_kpi@1.0.0")).closest("tr")!;
      expect(within(kpi).getByText("Riêng của công ty")).toBeTruthy();
      // The platform's version applies, and it is also what the platform ships.
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
      // Nothing on this page decides: the decision is the platform's.
      expect(screen.queryByRole("button", { name: /^Duyệt/ })).toBeNull();
    },
    SLOW,
  );

  it(
    "proposes a whole document for one key with a key minted for the press, and sends no text that is not JSON",
    async () => {
      render(
        <UiProvider>
          <RulesPage />
        </UiProvider>,
      );
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
        }),
      );
      const editor = (await screen.findByRole("textbox", {
        name: "Tài liệu (JSON)",
      })) as HTMLTextAreaElement;
      expect(JSON.parse(editor.value)).toEqual(KPI_DOC);

      fireEvent.change(editor, { target: { value: "{ not json" } });
      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      expect(
        await screen.findByText(/Tài liệu phải là JSON hợp lệ/),
      ).toBeTruthy();
      expect(api.proposeRule).not.toHaveBeenCalled();

      const next = { ...KPI_DOC, version: "1.0.2" };
      fireEvent.change(editor, { target: { value: JSON.stringify(next) } });
      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      await waitFor(() => expect(api.proposeRule).toHaveBeenCalledTimes(1));
      const [key, body, idempotency] = api.proposeRule.mock
        .calls[0] as unknown as [string, unknown, string];
      expect([key, body]).toEqual(["sales_kpi", { document: next }]);
      expect(idempotency).toMatch(/^[0-9a-f-]{36}$/);
      await waitFor(() => expect(api.rules).toHaveBeenCalledTimes(2));
    },
    SLOW,
  );

  it(
    "says which company version the editor opens with",
    async () => {
      render(
        <UiProvider>
          <RulesPage />
        </UiProvider>,
      );
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
        }),
      );
      expect(
        await screen.findByText(/phiên bản công ty đang áp dụng/),
      ).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
      await waitFor(() =>
        expect(screen.queryByText(/phiên bản công ty đang áp dụng/)).toBeNull(),
      );

      // The order rules apply as the platform ships them: the editor opens
      // the company's latest version, the one waiting on its approval.
      fireEvent.click(
        screen.getByRole("button", {
          name: "Đề xuất phiên bản mới: Quy tắc kiểm tra đơn hàng",
        }),
      );
      expect(
        await screen.findByText(/phiên bản gần nhất của công ty/),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "asks before closing an edited document, and keeps it on Tiếp tục sửa",
    async () => {
      render(
        <UiProvider>
          <RulesPage />
        </UiProvider>,
      );
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
        }),
      );
      const editor = (await screen.findByRole("textbox", {
        name: "Tài liệu (JSON)",
      })) as HTMLTextAreaElement;
      const edited = JSON.stringify({ ...KPI_DOC, target: 0.95 });
      fireEvent.change(editor, { target: { value: edited } });

      fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
      expect(
        (await screen.findAllByText("Bỏ tài liệu đang sửa?")).length,
      ).toBeGreaterThan(0);
      fireEvent.click(screen.getByRole("button", { name: "Tiếp tục sửa" }));
      // The drawer stays open with what was typed. (antd's close animation
      // never ends in jsdom, so the dismissed dialog is not asserted gone.)
      expect(
        (
          screen.getByRole("textbox", {
            name: "Tài liệu (JSON)",
          }) as HTMLTextAreaElement
        ).value,
      ).toBe(edited);

      fireEvent.click(screen.getByRole("button", { name: "Hủy" }));
      const discard = await screen.findAllByRole("button", {
        name: "Bỏ thay đổi",
      });
      fireEvent.click(discard[discard.length - 1]!);
      await waitFor(() =>
        expect(
          screen.queryByRole("textbox", { name: "Tài liệu (JSON)" }),
        ).toBeNull(),
      );
      expect(api.proposeRule).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it("draws the forbidden state, and asks nothing, without sales.rules.propose", () => {
    scopes = ["sales.case.read"];
    render(
      <UiProvider>
        <RulesPage />
      </UiProvider>,
    );

    expect(
      screen.getByText(/Quyền của bạn trong không gian làm việc này/),
    ).toBeTruthy();
    expect(api.rules).not.toHaveBeenCalled();
  });
});
