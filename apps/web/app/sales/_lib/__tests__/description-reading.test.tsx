import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { DescriptionReadingPanel } from "../../orders/[caseId]/description-reading";

type Reading = NonNullable<
  SalesSchemas["OrderLineView"]["basis"]["description_reading"]
>;

const base = {
  prompt: "sales.description_attributes@1.0.0",
  model_profile: "onprem",
};

afterEach(cleanup);

describe("what a model read from a description (ticket 28)", () => {
  it("marks each label as the model's and each number as DW1's own", () => {
    const reading: Reading = {
      ...base,
      outcome: "read",
      reason: null,
      spans: [
        {
          attribute: "colour",
          span: "màu đỏ",
          start: 60,
          end: 66,
          value: "red",
          read_by: "model",
        },
        {
          attribute: "gauge",
          span: "AWG24",
          start: 9,
          end: 14,
          value: "AWG24",
          read_by: "code",
        },
      ],
    };
    render(
      <UiProvider>
        <DescriptionReadingPanel reading={reading} />
      </UiProvider>,
    );
    const table = screen.getByRole("region", { name: "Mô hình đọc mô tả" });
    const rows = within(table).getAllByRole("row");
    // The header, then one row per attribute, each saying who read it in words.
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByText("Màu")).toBeTruthy();
    expect(within(rows[1]!).getByText("màu đỏ")).toBeTruthy();
    expect(within(rows[1]!).getByText("Mô hình đọc, cần kiểm")).toBeTruthy();
    expect(within(rows[2]!).getByText("DW1 tính từ chữ")).toBeTruthy();
  }, 20_000);

  it("says DW1 could not read the description when the model gave no answer", () => {
    render(
      <UiProvider>
        <DescriptionReadingPanel
          reading={{ ...base, outcome: "unavailable", reason: null, spans: [] }}
        />
      </UiProvider>,
    );
    expect(screen.getByText("DW1 không đọc được mô tả")).toBeTruthy();
    expect(
      screen.queryByRole("region", { name: "Mô hình đọc mô tả" }),
    ).toBeNull();
  });

  it("names the check that refused a reading", () => {
    render(
      <UiProvider>
        <DescriptionReadingPanel
          reading={{
            ...base,
            outcome: "not_understood",
            reason: "text_uncovered",
            spans: [],
          }}
        />
      </UiProvider>,
    );
    expect(screen.getByText(/còn chữ không thuộc thuộc tính nào/)).toBeTruthy();
  });

  it("draws nothing for a line no model was asked about", () => {
    const { container } = render(
      <UiProvider>
        <DescriptionReadingPanel reading={null} />
      </UiProvider>,
    );
    expect(container.textContent).toBe("");
  });
});
