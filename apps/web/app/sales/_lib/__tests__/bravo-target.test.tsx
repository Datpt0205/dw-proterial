import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import {
  BravoTargetCard,
  NO_RULES_SCOPE,
} from "../../_components/bravo-target";
import { appliesAtOnceFor } from "../rules";

type Targets = SalesSchemas["BravoTargetsView"];

const PRODUCTION: Targets = {
  connected: true,
  current: "production",
  uat: true,
  production: false,
};

function card(
  targets: Targets | null,
  mayPropose: boolean,
  onSwitch = vi.fn(),
) {
  render(
    <UiProvider>
      <BravoTargetCard
        targets={targets}
        mayPropose={mayPropose}
        onSwitch={onSwitch}
      />
    </UiProvider>,
  );
  return screen.getByRole("button", {
    name: "Đề xuất đổi Bravo DW1 đọc và ghi",
  }) as HTMLButtonElement;
}

afterEach(cleanup);

describe("the Bravo target switch on the rules page (ticket 85)", () => {
  it("shows the Bravo in use and the gateway's answer for each", () => {
    card(PRODUCTION, true);
    expect(
      screen.getByText("Bravo thật", { selector: "span.ant-tag" }),
    ).toBeTruthy();
    expect(screen.getByText("Đã có tài khoản")).toBeTruthy();
    expect(
      screen.getByText("Chưa có tài khoản: mọi lần đọc và ghi bị từ chối"),
    ).toBeTruthy();
  });

  it("opens the proposal for whoever may propose a rule", () => {
    const onSwitch = vi.fn();
    const button = card(PRODUCTION, true, onSwitch);
    fireEvent.click(button);
    expect(onSwitch).toHaveBeenCalledOnce();
  });

  it("is disabled without the scope, with the reason", () => {
    const onSwitch = vi.fn();
    const button = card(PRODUCTION, false, onSwitch);
    expect(button.disabled).toBe(true);
    expect(screen.getByText(NO_RULES_SCOPE)).toBeTruthy();
    fireEvent.click(button);
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it("says so when the gateway did not answer, and names no Bravo", () => {
    card(
      { connected: false, current: null, uat: false, production: false },
      true,
    );
    expect(screen.getByText(/Chưa hỏi được gateway Bravo/)).toBeTruthy();
    expect(screen.queryByText("Bravo UAT")).toBeNull();
  });
});

describe("who decides a switch of Bravo (tickets 63, 85)", () => {
  it("never words the head's own Bravo version as applied at once", () => {
    expect(appliesAtOnceFor("sales_bravo_writes", true)).toBe(false);
    expect(appliesAtOnceFor("sales_kpi", true)).toBe(true);
    expect(appliesAtOnceFor("sales_kpi", false)).toBe(false);
  });
});
