"use client";

import { useState } from "react";
import { Button, theme } from "antd";
import { AppShell } from "@dw/ui";

/** The client half of the fixture: page.tsx decides whether it exists. */
export function LayerCheckFixture() {
  const { token } = theme.useToken();
  const [navigated, setNavigated] = useState("");
  // Each Tailwind breakpoint beside the antd token it must equal. The class
  // names are written out whole, because Tailwind only builds what it reads.
  const breakpoints = [
    ["sm", token.screenSM, "hidden sm:inline"],
    ["md", token.screenMD, "hidden md:inline"],
    ["lg", token.screenLG, "hidden lg:inline"],
    ["xl", token.screenXL, "hidden xl:inline"],
    ["2xl", token.screenXXL, "hidden 2xl:inline"],
  ] as const;
  return (
    <AppShell
      brand={<span>Layer check</span>}
      items={[
        {
          key: "here",
          label: (
            <a href="/dev-login/layer-check" tabIndex={-1}>
              Trang này
            </a>
          ),
        },
        {
          key: "other",
          label: (
            <a href="#other" tabIndex={-1}>
              Trang khác
            </a>
          ),
        },
      ]}
      onNavigate={setNavigated}
      selectedKey="here"
      navLabel="Điều hướng chính"
      menuLabel="Mở menu"
    >
      {/* Padding, because antd's Button sets padding too: the utility wins
          only when the layers are in order. A margin would win either way. */}
      <Button type="primary" className="px-10">
        Kiểm tra
      </Button>
      {/* What the shell's onNavigate was last called with. */}
      <output data-testid="navigated">{navigated}</output>
      {breakpoints.map(([name, min, className]) => (
        <span
          key={name}
          className={className}
          data-testid={`tailwind-${name}`}
          data-antd-min={min}
        >
          {name}
        </span>
      ))}
    </AppShell>
  );
}
