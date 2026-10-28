import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { ListToolbar } from "../../_components/list-parts";

afterEach(cleanup);

function toolbar(query: string, onQuery: (q: string) => void) {
  return (
    <UiProvider>
      <ListToolbar
        tabs={[{ value: "all", label: "Tất cả", count: 3 }]}
        tab="all"
        onTab={() => undefined}
        query={query}
        onQuery={onQuery}
        placeholder="Số PO"
        sorts={[{ value: "new", label: "Mới nhất" }]}
        sort="new"
        onSort={() => undefined}
      />
    </UiProvider>
  );
}

describe("the list search (2026-10-28: fast typing lost characters)", () => {
  it("keeps every key in the field and hands the list the whole text once", async () => {
    const onQuery = vi.fn();
    render(toolbar("", onQuery));
    const box = screen.getByRole("textbox", { name: "Tìm trong danh sách" });
    for (const text of ["v", "vl", "vlx", "vlx ", "vlx p", "vlx po"]) {
      fireEvent.change(box, { target: { value: text } });
    }
    expect((box as HTMLInputElement).value).toBe("vlx po");
    expect(onQuery).not.toHaveBeenCalled();
    await waitFor(() => expect(onQuery).toHaveBeenCalledWith("vlx po"));
    expect(onQuery).toHaveBeenCalledTimes(1);
  });

  it("follows a query changed from elsewhere (Xóa bộ lọc, Back)", () => {
    const { rerender } = render(toolbar("vlx", vi.fn()));
    const box = screen.getByRole("textbox", { name: "Tìm trong danh sách" });
    expect((box as HTMLInputElement).value).toBe("vlx");
    rerender(toolbar("", vi.fn()));
    expect((box as HTMLInputElement).value).toBe("");
  });
});
