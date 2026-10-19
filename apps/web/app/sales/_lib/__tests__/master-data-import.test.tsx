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
import { AN, GIANG } from "./fixtures";
import {
  diffSummary,
  shownImport,
  sourceLabel,
  toBase64,
  uploadBlocked,
  type CatalogImport,
  type CatalogListState,
  type CatalogPreview,
} from "../catalog";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const SNAPSHOT = "0aa10aa0-c939-7000-8539-31fd3e621710";
const APPROVAL = "0aa10aa0-c939-7000-8539-31fd3e621711";

function snapshot(overrides: Partial<CatalogImport> = {}): CatalogImport {
  return {
    snapshot_id: SNAPSHOT,
    catalog_list: "customers",
    status: "parsed",
    source: "file",
    file_name: "khach-hang.xlsx",
    file_sha256: "a".repeat(64),
    imported_by: AN,
    imported_at: "2026-10-19T02:00:00Z",
    as_of: "2026-10-19T02:00:00Z",
    error: null,
    row_count: 7,
    rejected_count: 1,
    submitted_by: null,
    submitted_at: null,
    approval_id: null,
    decided_by: null,
    decided_at: null,
    comment: null,
    ...overrides,
  };
}

function state(overrides: Partial<CatalogListState> = {}): CatalogListState {
  return {
    catalog_list: "customers",
    label: "Khách hàng",
    in_force: { source: "mock", as_of: "2026-10-02T11:00:00Z", snapshot: null },
    open: null,
    history: [],
    can_import: true,
    ...overrides,
  };
}

const PREVIEW: CatalogPreview = {
  snapshot: snapshot(),
  compared_with: {
    source: "mock",
    as_of: "2026-10-02T11:00:00Z",
    snapshot: null,
  },
  columns: ["Mã khách hàng", "Tên khách hàng"],
  added: [
    {
      key: "NEWC",
      cells: { "Mã khách hàng": "NEWC", "Tên khách hàng": "New Co" },
    },
  ],
  changed: [
    {
      key: "VLX",
      changes: [
        { column: "Tên khách hàng", old: "Velatrix", new: "Velatrix Renamed" },
      ],
    },
  ],
  removed: [
    {
      key: "OLD",
      cells: { "Mã khách hàng": "OLD", "Tên khách hàng": "Old Co" },
    },
  ],
  unchanged: 5,
  rejected: [
    { row: 9, column: "NOC đã xác nhận", reason: "ghi Có hoặc Không" },
  ],
  rejected_count: 1,
  unknown_headers: ["Ghi chú"],
};

const api = {
  catalogPreview: vi.fn(async () => PREVIEW),
  submitCatalog: vi.fn(async () => snapshot({ status: "submitted" })),
  uploadCatalog: vi.fn(async () => snapshot({ status: "queued" })),
  catalogTemplate: vi.fn(async () => new Blob(["x"])),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { ImportPanel } from "../../master-data/import-panel";

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("the master-data import's logic (ticket 41)", () => {
  it("says whether a list is the sample data or an approved import, by whom", () => {
    const name = (id: string | null | undefined) =>
      id === GIANG ? "Giang" : "An";
    expect(sourceLabel(state().in_force, name)).toMatchObject({ tone: "warn" });
    expect(sourceLabel(state().in_force, name).text).toMatch(/^Dữ liệu mẫu/);
    const approved = snapshot({ status: "approved", decided_by: GIANG });
    const label = sourceLabel(
      { source: "file", as_of: approved.as_of, snapshot: approved },
      name,
    );
    expect(label.tone).toBe("ok");
    expect(label.text).toMatch(/^Bản nhập ngày .* bởi An, Giang duyệt$/);
  });

  it("refuses an upload in words without the scope or while one waits", () => {
    expect(uploadBlocked(state())).toBeNull();
    expect(uploadBlocked(state({ can_import: false }))).toMatch(
      /chưa có quyền/,
    );
    expect(
      uploadBlocked(state({ catalog_list: "quotations", can_import: false })),
    ).toMatch(/có giá/);
    expect(
      uploadBlocked(state({ open: snapshot({ status: "submitted" }) })),
    ).toMatch(/chờ duyệt/);
  });

  it("shows the open import, else the newest one when it failed", () => {
    const failed = snapshot({ status: "failed", error: "thiếu cột: Tháng" });
    expect(shownImport(state({ history: [failed] }))).toBe(failed);
    expect(
      shownImport(state({ history: [snapshot({ status: "approved" })] })),
    ).toBeNull();
  });

  it("encodes a file as base64 in chunks and counts the diff", () => {
    const bytes = new Uint8Array(100_000).fill(65);
    expect(atob(toBase64(bytes))).toHaveLength(100_000);
    expect(diffSummary(PREVIEW)).toBe(
      "Thêm 1 · Sửa 1 · Bỏ 1 · Giữ nguyên 5 · Bị loại 1 dòng",
    );
  });
});

describe("the import panel (ticket 41)", () => {
  it(
    "shows the preview of a parsed import, its rejected rows, and submits it with a key",
    async () => {
      const changed = vi.fn();
      render(
        <UiProvider>
          <ImportPanel
            state={state({ open: snapshot() })}
            onChanged={changed}
          />
        </UiProvider>,
      );
      expect(screen.getByText("Dữ liệu mẫu")).toBeTruthy();
      expect(
        await screen.findByText(
          "Thêm 1 · Sửa 1 · Bỏ 1 · Giữ nguyên 5 · Bị loại 1 dòng",
        ),
      ).toBeTruthy();
      const changes = screen.getByRole("region", { name: "Dòng thay đổi" });
      expect(
        within(changes).getByText(/Velatrix → Velatrix Renamed/),
      ).toBeTruthy();
      const rejected = screen.getByRole("region", {
        name: "Dòng bị loại (không áp dụng)",
      });
      expect(within(rejected).getByText("ghi Có hoặc Không")).toBeTruthy();
      expect(
        screen.getByText(/Cột không dùng \(bỏ qua\): Ghi chú/),
      ).toBeTruthy();
      // Nothing on this page approves.
      expect(screen.queryByRole("button", { name: /^Duyệt/ })).toBeNull();

      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      await waitFor(() => expect(api.submitCatalog).toHaveBeenCalledTimes(1));
      const [id, key] = api.submitCatalog.mock.calls[0] as unknown as [
        string,
        string,
      ];
      expect(id).toBe(SNAPSHOT);
      expect(key).toMatch(/^[0-9a-f-]{36}$/);
      await waitFor(() => expect(changed).toHaveBeenCalled());
    },
    SLOW,
  );

  it(
    "links a submitted import to its approval and refuses another upload in words",
    async () => {
      render(
        <UiProvider>
          <ImportPanel
            state={state({
              open: snapshot({
                status: "submitted",
                submitted_by: AN,
                approval_id: APPROVAL,
              }),
            })}
            onChanged={vi.fn()}
          />
        </UiProvider>,
      );
      expect(
        screen
          .getByRole("link", { name: "Mở yêu cầu duyệt" })
          .getAttribute("href"),
      ).toBe(`/approvals/${APPROVAL}`);
      const upload = screen.getByRole("button", { name: "Nhập file" });
      expect((upload as HTMLButtonElement).disabled).toBe(true);
      expect(screen.getByText(/Đang có bản nhập chờ duyệt/)).toBeTruthy();
    },
    SLOW,
  );

  it(
    "draws a failed import with its reason and never asks for a preview",
    async () => {
      render(
        <UiProvider>
          <ImportPanel
            state={state({
              history: [
                snapshot({
                  status: "failed",
                  error: "thiếu cột: Tháng",
                  row_count: 0,
                }),
              ],
            })}
            onChanged={vi.fn()}
          />
        </UiProvider>,
      );
      expect(screen.getByText("thiếu cột: Tháng")).toBeTruthy();
      expect(api.catalogPreview).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "uploads a chosen file as base64 with a key minted for the press",
    async () => {
      const changed = vi.fn();
      const { container } = render(
        <UiProvider>
          <ImportPanel state={state()} onChanged={changed} />
        </UiProvider>,
      );
      const input = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement;
      expect(input.accept).toBe(".xlsx,.xls,.csv");
      const file = new File(["Tháng;Giá\n"], "lme.csv", { type: "text/csv" });
      fireEvent.change(input, { target: { files: [file] } });
      await waitFor(() => expect(api.uploadCatalog).toHaveBeenCalledTimes(1));
      const [list, body, key] = api.uploadCatalog.mock.calls[0] as unknown as [
        string,
        { file_name: string; content_b64: string },
        string,
      ];
      expect(list).toBe("customers");
      expect(body.file_name).toBe("lme.csv");
      expect(
        new TextDecoder().decode(
          Uint8Array.from(atob(body.content_b64), (c) => c.charCodeAt(0)),
        ),
      ).toBe("Tháng;Giá\n");
      expect(key).toMatch(/^[0-9a-f-]{36}$/);
      await waitFor(() => expect(changed).toHaveBeenCalled());
    },
    SLOW,
  );

  it(
    "disables the upload with the reason for a viewer without the scope",
    async () => {
      render(
        <UiProvider>
          <ImportPanel
            state={state({ can_import: false })}
            onChanged={vi.fn()}
          />
        </UiProvider>,
      );
      const upload = screen.getByRole("button", { name: "Nhập file" });
      expect((upload as HTMLButtonElement).disabled).toBe(true);
      expect(screen.getByText(/chưa có quyền nhập dữ liệu chủ/)).toBeTruthy();
      expect(
        (screen.getByRole("button", { name: "Tải mẫu" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
    },
    SLOW,
  );
});
