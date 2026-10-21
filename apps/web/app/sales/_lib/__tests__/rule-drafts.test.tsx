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
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";
import {
  draftChoices,
  draftOption,
  draftProblemText,
  machineRead,
  type PlatformDocument,
  type RuleDraft,
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

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) =>
      ["sales.case.read", "sales.rules.propose"].includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

function layout(
  sheet: string,
  mock: boolean,
  columns: [string, string][],
): Record<string, unknown> {
  return {
    schema_version: "1.0",
    policy_id: "sales_bravo_upload",
    policy_version: "1.1.0",
    mock,
    description: "",
    sheet_name: sheet,
    columns: columns.map(([field, header]) => ({ field, header })),
  };
}

const PLATFORM_DOC = layout("SO_IMPORT", true, [
  ["po_no", "SoPO"],
  ["line_no", "Dong"],
  ["prv_code", "MaHang"],
  ["quantity", "SoLuong"],
]);

const TEMPLATE = {
  sheet: "NhapDonBan",
  row: 3,
  headers: [
    ["A3", "Số đơn hàng"],
    ["B3", "Dòng"],
    ["C3", "Mã hàng"],
    ["D3", "Số lượng"],
    ["E3", "Ghi chú"],
  ].map(([ref, text], i) => ({ ref: ref!, column: i + 1, text: text! })),
};

const ID = "0aa10aa0-c939-7000-8539-31fd3e6217d1";

function draft(overrides: Partial<RuleDraft>): RuleDraft {
  return {
    draft_id: ID,
    rule_key: "sales_bravo_upload",
    status: "queued",
    requested_by: AN,
    requested_at: "2026-10-21T02:00:00Z",
    file_name: "mau.xlsx",
    file_sha256: "a".repeat(64),
    template: null,
    document: null,
    machine_read: [],
    evidence: {},
    problems: [],
    error: null,
    prompt_ref: null,
    model_profile: null,
    ...overrides,
  };
}

const READY = draft({
  status: "ready",
  template: TEMPLATE,
  document: layout("NhapDonBan", false, [
    ["po_no", "Số đơn hàng"],
    ["line_no", "Dòng"],
    ["prv_code", "Mã hàng"],
    ["quantity", "Số lượng"],
  ]),
  machine_read: [
    "sheet_name",
    "columns.0.field",
    "columns.0.header",
    "columns.3.field",
    "columns.3.header",
  ],
  evidence: {
    sheet_name: "NhapDonBan!A3:E3",
    "columns.0.field": "NhapDonBan!A3",
    "columns.0.header": "NhapDonBan!A3",
    "columns.3.field": "NhapDonBan!D3",
    "columns.3.header": "NhapDonBan!D3",
  },
  problems: [{ code: "column_unmapped", ref: "E3", header: "Ghi chú" }],
  prompt_ref: "sales.bravo_template_mapping@1.0.0",
  model_profile: "onprem",
});

const UNAVAILABLE = draft({
  status: "unavailable",
  template: TEMPLATE,
  document: { ...PLATFORM_DOC, sheet_name: "NhapDonBan" },
  machine_read: ["sheet_name"],
  evidence: { sheet_name: "NhapDonBan!A3:E3" },
  problems: [{ code: "model_not_configured" }],
});

const VIEW: View = {
  in_force: { sales_bravo_upload: "sales_bravo_upload@1.1.0" },
  layers: { sales_bravo_upload: "platform" },
  platform: [
    { key: "sales_bravo_upload", ref: "sales_bravo_upload@1.1.0" },
    { key: "sales_kpi", ref: "sales_kpi@1.0.0" },
  ],
  versions: [],
  draftable: ["sales_bravo_upload"],
};

const PLATFORM: PlatformDocument[] = [
  {
    key: "sales_bravo_upload",
    ref: "sales_bravo_upload@1.1.0",
    version: "1.1.0",
    current: true,
    document: PLATFORM_DOC,
  },
];

const api = {
  rules: vi.fn(async () => VIEW),
  proposeRule: vi.fn(),
  ruleSchema: vi.fn(async (key: string) => ({
    key,
    json_schema: SCHEMAS[key]!,
  })),
  rulePlatformDocuments: vi.fn(async () => PLATFORM),
  requestRuleDraft: vi.fn(async (...args: unknown[]) => (void args, draft({}))),
  ruleDraft: vi.fn(async (...args: unknown[]) => (void args, READY)),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import RulesPage from "../../rules/page";

const SLOW = 30_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPage() {
  render(
    <UiProvider>
      <RulesPage />
    </UiProvider>,
  );
}

async function openBravo() {
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Đề xuất phiên bản mới: Mẫu tệp nhập Bravo",
    }),
  );
  return screen.findByRole("button", { name: /Tạo từ tệp mẫu/ });
}

function upload() {
  const input = document.querySelector(
    'input[type="file"]',
  ) as HTMLInputElement;
  const file = new File(["PK"], "mau.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("a draft's logic (Tạo từ tệp mẫu)", () => {
  it("offers a draft to start from once it has a document, under its own id", () => {
    expect(draftOption(draft({}))).toBeNull();
    expect(draftOption(draft({ status: "failed", error: "x" }))).toBeNull();
    expect(draftOption(READY)).toMatchObject({
      id: `draft:${ID}`,
      ref: "sales_bravo_upload@1.1.0",
      inForce: false,
      document: READY.document,
    });
  });

  it("names each machine-read value with its cell and what it read", () => {
    expect(machineRead(READY)["columns.3.header"]).toEqual({
      evidence: "NhapDonBan!D3",
      value: "Số lượng",
    });
    expect(machineRead(UNAVAILABLE)).toEqual({
      sheet_name: { evidence: "NhapDonBan!A3:E3", value: "NhapDonBan" },
    });
    expect(draftChoices(UNAVAILABLE)).toEqual({
      "columns[].header": [
        "Số đơn hàng",
        "Dòng",
        "Mã hàng",
        "Số lượng",
        "Ghi chú",
      ],
    });
    expect(draftChoices(draft({}))).toEqual({});
  });

  it("says each problem in words, a field by its label", () => {
    expect(
      draftProblemText({ code: "required_missing", field: "quantity" }),
    ).toBe(
      "Mẫu không có cột cho “Số lượng”: tệp nhập Bravo bắt buộc có giá trị này.",
    );
    expect(
      draftProblemText({ code: "header_not_in_template", field: "po_no" }),
    ).toMatch(/^“Số PO”: DW1 nêu một tiêu đề không có nguyên văn/);
    expect(
      draftProblemText({
        code: "column_unmapped",
        ref: "E3",
        header: "Ghi chú",
      }),
    ).toMatch(/^Cột E3 “Ghi chú” của mẫu không ứng với giá trị nào/);
  });
});

describe("Tạo từ tệp mẫu on the rules page", () => {
  it(
    "uploads a template, polls while it is read, and opens the draft with its machine-read values marked",
    async () => {
      renderPage();
      await openBravo();
      upload();
      await waitFor(() =>
        expect(api.requestRuleDraft).toHaveBeenCalledTimes(1),
      );
      const [key, body, idempotency] = api.requestRuleDraft.mock.calls[0] as [
        string,
        { file_name: string; content_b64: string },
        string,
      ];
      expect([key, body]).toEqual([
        "sales_bravo_upload",
        { file_name: "mau.xlsx", content_b64: "UEs=" },
      ]);
      expect(idempotency).toMatch(/^[0-9a-f-]{36}$/);
      expect(await screen.findByText("Đang đọc tệp: mau.xlsx")).toBeTruthy();

      // Asked again after the poll interval, then opened as the start.
      expect(
        await screen.findByText("Đã đọc xong: mau.xlsx", undefined, {
          timeout: 10_000,
        }),
      ).toBeTruthy();
      expect(api.ruleDraft).toHaveBeenCalledWith(ID);
      expect(
        await screen.findByText("Bản nháp từ tệp mau.xlsx · Đã đọc xong"),
      ).toBeTruthy();
      await waitFor(() => {
        const headers = screen.getAllByRole("combobox", {
          name: "Tiêu đề cột",
        }) as HTMLInputElement[];
        expect(headers.map((h) => h.value)).toEqual([
          "Số đơn hàng",
          "Dòng",
          "Mã hàng",
          "Số lượng",
        ]);
      });
      await waitFor(() =>
        expect(screen.getAllByText("Đọc từ NhapDonBan!D3")).toHaveLength(2),
      );
      expect(screen.getAllByText("Máy đọc").length).toBeGreaterThanOrEqual(5);
      // The template's column no value takes, said in the notice.
      expect(screen.getByText(/Cột E3 “Ghi chú” của mẫu/)).toBeTruthy();
    },
    SLOW,
  );

  it(
    "drops the mark from a value the person changed",
    async () => {
      api.requestRuleDraft.mockResolvedValueOnce(READY);
      renderPage();
      await openBravo();
      upload();
      await waitFor(() =>
        expect(screen.getAllByText("Đọc từ NhapDonBan!D3")).toHaveLength(2),
      );
      const quantity = screen.getAllByRole("combobox", {
        name: "Tiêu đề cột",
      })[3]!;
      fireEvent.change(quantity, { target: { value: "SL" } });
      await waitFor(() =>
        expect(screen.getAllByText("Đọc từ NhapDonBan!D3")).toHaveLength(1),
      );
    },
    SLOW,
  );

  it(
    "without a model, opens the version in force with only the sheet read and the template's headers offered",
    async () => {
      api.requestRuleDraft.mockResolvedValueOnce(UNAVAILABLE);
      renderPage();
      await openBravo();
      upload();
      expect(
        await screen.findByText("Chưa ánh xạ được bằng mô hình: mau.xlsx"),
      ).toBeTruthy();
      expect(screen.getByText(/Máy chủ này chưa có mô hình/)).toBeTruthy();
      expect(
        screen.getByText(
          /Tiêu đề của mẫu \(sheet NhapDonBan, hàng 3\): Số đơn hàng · Dòng/,
        ),
      ).toBeTruthy();
      // The columns are the version in force, not guessed; offered as choices.
      await waitFor(() => {
        const headers = screen.getAllByRole("combobox", {
          name: "Tiêu đề cột",
        }) as HTMLInputElement[];
        expect(headers.map((h) => h.value)).toEqual([
          "SoPO",
          "Dong",
          "MaHang",
          "SoLuong",
        ]);
      });
      expect(screen.getAllByText("Máy đọc")).toHaveLength(1);
      expect(screen.getByText("Đọc từ NhapDonBan!A3:E3")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "says why a file could not be read, and offers nothing to start from",
    async () => {
      api.requestRuleDraft.mockResolvedValueOnce(
        draft({ status: "failed", error: "tệp không phải bảng tính Excel" }),
      );
      renderPage();
      await openBravo();
      upload();
      const notice = (
        await screen.findByText("Không đọc được tệp: mau.xlsx")
      ).closest(".ant-alert")!;
      expect(
        within(notice as HTMLElement).getByText(
          "tệp không phải bảng tính Excel",
        ),
      ).toBeTruthy();
      expect(screen.queryByText(/Bản nháp từ tệp/)).toBeNull();
    },
    SLOW,
  );

  it(
    "offers no template upload for a key that is not drafted",
    async () => {
      renderPage();
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Đề xuất phiên bản mới: Chỉ tiêu KPI",
        }),
      );
      await screen.findByText("Bắt đầu từ phiên bản");
      expect(
        screen.queryByRole("button", { name: /Tạo từ tệp mẫu/ }),
      ).toBeNull();
    },
    SLOW,
  );
});
