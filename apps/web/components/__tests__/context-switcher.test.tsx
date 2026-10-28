import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { RobotOutlined } from "@ant-design/icons";
import type { NavGroup } from "../../lib/nav/types";
import { ContextSwitcher } from "../context-switcher";

/**
 * Two Digital Workers for one person (2026-10-28): the brand names the one in
 * use and switches to the other's first page.
 */
const group = (key: string, product: string, href: string): NavGroup => ({
  key,
  label: product,
  icon: RobotOutlined,
  context: { product, roleKeyPrefix: `${key}_` },
  items: [
    { href, label: "Việc cần làm", hint: "Việc chờ bạn", icon: RobotOutlined },
  ],
});

const DW1 = group("sales", "DW1 Đơn hàng & Báo giá", "/sales");
const DW2 = group("purchasing", "DW2 Mua hàng", "/purchasing");

afterEach(cleanup);

describe("the Digital Worker switch", () => {
  it("names the one in use and opens the other's first page", async () => {
    const onPick = vi.fn();
    render(
      <UiProvider>
        <ContextSwitcher contexts={[DW1, DW2]} active={DW1} onPick={onPick} />
      </UiProvider>,
    );
    const button = screen.getByRole("button", {
      name: "Đang dùng DW1 Đơn hàng & Báo giá. Chọn Digital Worker khác",
    });
    fireEvent.click(button);
    fireEvent.click(await screen.findByText("DW2 Mua hàng"));
    expect(onPick).toHaveBeenCalledWith("/purchasing");
  });
});
