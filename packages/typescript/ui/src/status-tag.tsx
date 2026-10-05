"use client";

import type { ReactNode } from "react";
import { Tag, Tooltip } from "antd";
import { STATUS_TAG_SHAPE, STATUS_TONES, type StatusTone } from "./theme";

export interface StatusTagProps {
  /** The tone from the label table; the words carry the meaning, never it alone. */
  tone: StatusTone;
  icon?: ReactNode;
  /** Set for a code or an identifier: monospace, square-ish corners. */
  mono?: boolean;
  /** What the status means, on hover, focus and tap. */
  tip?: ReactNode;
  children: ReactNode;
}

/**
 * The one status tag (the prototype's label-table chip): a pill with a tint,
 * the text drawn on it, and an icon, all read from the theme's
 * `STATUS_TONES`. A context keeps its own table from code to tone and words;
 * the look is decided here once, so the same state looks the same on every
 * screen (ui-quality §1) and every tone's text passes on its tint (§12).
 */
export function StatusTag({ tone, icon, mono, tip, children }: StatusTagProps) {
  const { bg, fg, border } = STATUS_TONES[tone];
  const tag = (
    <Tag
      variant={border ? "outlined" : "filled"}
      icon={icon}
      className="me-0"
      style={{
        backgroundColor: bg,
        color: fg,
        borderColor: border ?? "transparent",
        borderStyle: tone === "unk" ? "dashed" : "solid",
        borderRadius: mono
          ? STATUS_TAG_SHAPE.codeRadius
          : STATUS_TAG_SHAPE.radius,
        fontWeight: mono
          ? STATUS_TAG_SHAPE.codeWeight
          : STATUS_TAG_SHAPE.weight,
        fontFamily: mono ? "var(--ant-font-family-code)" : undefined,
        paddingInline: STATUS_TAG_SHAPE.paddingInline,
      }}
      tabIndex={tip ? 0 : undefined}
    >
      {children}
    </Tag>
  );
  return tip ? <Tooltip title={tip}>{tag}</Tooltip> : tag;
}
