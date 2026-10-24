import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type View = SalesSchemas["CaseActivityView"];
type Entry = SalesSchemas["ActivityEntry"];

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope === "sales.case.read",
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const CASE = "0aa10aa0-c939-7000-8539-31fd3e6217aa";

function entry(overrides: Partial<Entry> = {}): Entry {
  return {
    step: "description_attributes",
    process_steps: ["O2"],
    kind: "read",
    occurred_at: "2026-10-20T02:00:00Z",
    calls: 1,
    duration_ms: 1_240,
    model: "qwen3.5-9b-dw",
    model_profile: "sales_local",
    prompt: "sales.description_attributes@1.0.0",
    message_id: "M07",
    line_no: 2,
    check: { result: "passed", reason_code: null },
    handled_by: "dw1",
    taken_over_by: null,
    produced: [
      {
        field: "family",
        value: "CVV",
        line_no: 2,
        anchor: { line_no: 2, field: "description" },
      },
      {
        field: "gauge",
        value: "2.5",
        line_no: 2,
        anchor: { line_no: 2, field: "description" },
      },
    ],
    refusals: {},
    ...overrides,
  };
}

const ENTRIES: Entry[] = [
  entry(),
  entry({
    kind: "check",
    line_no: 3,
    occurred_at: "2026-10-20T02:00:01Z",
    check: { result: "refused", reason_code: "span_not_found" },
    handled_by: "person",
    taken_over_by: AN,
    produced: [],
    calls: 0,
    duration_ms: null,
  }),
  entry({
    step: "message_intent",
    process_steps: ["O1", "Q1"],
    kind: "model_unavailable",
    line_no: null,
    occurred_at: "2026-10-21T03:00:00Z",
    check: { result: "not_run", reason_code: null },
    handled_by: "person",
    model: null,
    prompt: "sales.message_intent@1.0.0",
    produced: [],
    duration_ms: 30_000,
  }),
  entry({
    step: "rfq_extraction",
    process_steps: ["Q1"],
    line_no: null,
    occurred_at: "2026-10-22T04:00:00Z",
    prompt: "sales.rfq_extraction@1.0.0",
    produced: [
      {
        field: "quote_due",
        value: "2026-10-30",
        line_no: null,
        anchor: null,
      },
    ],
    refusals: { description_not_found: 2 },
  }),
];

const api = {
  caseActivity: vi.fn(async (): Promise<View> => ({
    case_kind: "order",
    case_id: CASE,
    entries: ENTRIES,
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { CaseActivity } from "../../_components/case-activity";

const onOpenSource = vi.fn();

function renderSection() {
  render(
    <UiProvider>
      <CaseActivity
        kind="order"
        caseId={CASE}
        version={3}
        onOpenSource={onOpenSource}
      />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const items = () => [...document.querySelectorAll("[data-activity]")];

describe("DW1 đã làm gì on a case (slice 3)", () => {
  it("lists what each model step did, oldest first, with its result in words", async () => {
    renderSection();
    // Loading: the section's shape, before the entries.
    expect(document.querySelector(".ant-skeleton")).not.toBeNull();
    await screen.findAllByText("Đọc mô tả hàng chưa có trong convert list");
    expect(api.caseActivity).toHaveBeenCalledWith("order", CASE);
    const [read, refused, unanswered, request] = items() as HTMLElement[];
    expect(items()).toHaveLength(4);

    expect(read!.textContent).toContain("Đã chấp nhận");
    expect(read!.textContent).toContain("DW1 đọc · dòng 2");
    expect(read!.textContent).toContain("Dòng 2 · Họ cáp: CVV");
    expect(read!.textContent).toContain("Dòng 2 · Tiết diện: 2.5");
    // Model, prompt and time, secondary.
    expect(read!.textContent).toContain(
      "09:00 20/10/2026 · mô hình qwen3.5-9b-dw · sales.description_attributes@1.0.0 · 1 lần gọi, 1,2 giây",
    );

    expect(refused!.textContent).toContain("Chuyển cho người");
    expect(refused!.textContent).toContain(
      "Lý do: Chữ mô hình chỉ ra không có trong mô tả",
    );
    expect(refused!.textContent).toContain("Người tiếp nhận: An (bạn)");

    expect(unanswered!.textContent).toContain("Model không trả lời");
    expect(unanswered!.textContent).toContain(
      "Người tiếp nhận: chưa ai tiếp nhận",
    );
    expect(unanswered!.textContent).toContain("mô hình không rõ");

    expect(request!.textContent).toContain("Hạn báo giá: 30/10/2026");
    expect(request!.textContent).toContain(
      "DW1 bỏ qua: Mô tả: không tìm thấy trong thư chữ mô hình chỉ ra (2)",
    );
  });

  it("opens the case's source at the place a value was read, once per place", async () => {
    renderSection();
    await screen.findByText("DW1 đã làm gì");
    await screen.findAllByText("Đã chấp nhận");
    const read = items()[0] as HTMLElement;
    const open = within(read).getAllByRole("button", { name: /^Xem nguồn/ });
    expect(open).toHaveLength(1);
    expect(open[0]!.textContent).toBe("Xem nguồn: Dòng 2 · Mô tả");
    fireEvent.click(open[0]!);
    expect(onOpenSource).toHaveBeenCalledWith("description", 2);
    // A value with no anchor offers no way to a source it does not have.
    expect(
      within(items()[3] as HTMLElement).queryByRole("button", {
        name: /^Xem nguồn/,
      }),
    ).toBeNull();
  });

  it("shows only what the server sent: no price when it left the price out", async () => {
    api.caseActivity.mockResolvedValueOnce({
      case_kind: "quote",
      case_id: CASE,
      entries: [ENTRIES[3]!],
    });
    renderSection();
    await screen.findByText(/Hạn báo giá: 30\/10\/2026/);
    expect(document.body.textContent).not.toContain("Giá khách nêu");
    expect(document.body.textContent).not.toContain("Giá mong muốn");
    cleanup();

    // Sent to someone who may read prices, the same entry carries them.
    const priced = entry({
      ...ENTRIES[3]!,
      produced: [
        ...ENTRIES[3]!.produced,
        {
          field: "stated_target_price",
          value: "1.25",
          line_no: 1,
          anchor: { line_no: 1, field: "stated_target_price" },
        },
      ],
    });
    api.caseActivity.mockResolvedValueOnce({
      case_kind: "quote",
      case_id: CASE,
      entries: [priced],
    });
    renderSection();
    expect(
      await screen.findByText("Dòng 1 · Giá khách nêu: 1.25"),
    ).toBeTruthy();
  });

  it("says a step's calls and time once per mail, not on each of its lines", async () => {
    // The server repeats the mail's timing on every row of the step.
    const timed = { calls: 3, duration_ms: 4_200 };
    api.caseActivity.mockResolvedValueOnce({
      case_kind: "order",
      case_id: CASE,
      entries: [
        entry({ ...timed, line_no: 1 }),
        entry({ ...timed, line_no: 2 }),
        entry({ ...timed, line_no: 3 }),
        entry({ ...timed, message_id: "M08", line_no: 1 }),
      ],
    });
    renderSection();
    await screen.findAllByText("Đọc mô tả hàng chưa có trong convert list");
    const texts = (items() as HTMLElement[]).map((i) => i.textContent ?? "");
    expect(texts[0]).toContain(
      "3 lần gọi, 4,2 giây cho cả thư (3 mục của bước này)",
    );
    expect(texts[1]).not.toContain("lần gọi");
    expect(texts[2]).not.toContain("lần gọi");
    // Another mail's step is timed on its own.
    expect(texts[3]).toContain("3 lần gọi, 4,2 giây");
    expect(texts[3]).not.toContain("cho cả thư");
  });

  it("says when DW1 has done nothing on the case", async () => {
    api.caseActivity.mockResolvedValueOnce({
      case_kind: "order",
      case_id: CASE,
      entries: [],
    });
    renderSection();
    expect(
      await screen.findByText("DW1 chưa làm gì ở hồ sơ này."),
    ).toBeTruthy();
  });

  it("draws a failure with its request id, and a refusal as no access", async () => {
    api.caseActivity.mockRejectedValueOnce(
      new ApiError(500, {
        code: "internal",
        message: "Máy chủ gặp lỗi.",
        details: {},
        request_id: "req-activity-1",
      }),
    );
    renderSection();
    expect(await screen.findByText(/req-activity-1/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeTruthy();
    cleanup();

    api.caseActivity.mockRejectedValueOnce(
      new ApiError(403, {
        code: "permission_denied",
        message: "Bạn không có quyền xem hồ sơ này.",
        details: {},
        request_id: "req-activity-2",
      }),
    );
    renderSection();
    expect(
      await screen.findByText("Bạn không có quyền xem mục này"),
    ).toBeTruthy();
  });
});
