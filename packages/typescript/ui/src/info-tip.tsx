"use client";

import type { ReactNode } from "react";
import { Button, Popover } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";

export interface InfoTipProps {
  /** What the button says to a screen reader: "Giải thích <what>". */
  label?: string;
  children: ReactNode;
}

/**
 * The one "details on click" for an explanation a page does not need on its
 * first screenful (Đạt, 2026-11-01: only what a person acts on is shown; how
 * something works opens when asked). A "?" button opens a popover on click,
 * tap and keyboard; a tooltip would open on hover alone, which touch lacks.
 * Never for a fact a decision needs, nor a disabled control's reason
 * (ui-quality §2, §5): those stay on the page.
 */
export function InfoTip({ label = "Giải thích", children }: InfoTipProps) {
  return (
    <Popover
      trigger="click"
      content={<div style={{ maxWidth: 380 }}>{children}</div>}
    >
      <Button
        type="text"
        size="small"
        shape="circle"
        icon={<QuestionCircleOutlined aria-hidden />}
        aria-label={label}
      />
    </Popover>
  );
}
