"use client";

import { LockOutlined } from "@ant-design/icons";
import { Alert, Tooltip } from "antd";

/** What every masked cell reads, and what a test looks for. */
export const MASKED_LABEL = "Đã ẩn";

export interface MaskedValueProps {
  /**
   * Who can see it, said once: in the tooltip of a cell, and as the text of a
   * region. Never the value, never a hint of its size.
   */
  sentence: string;
}

/**
 * A value the viewer may not see, drawn as locked rather than blank
 * (ui-quality §6): the lock and "Đã ẩn", never "0" and never "—", which read as
 * "there is no price". The API has already left the value out; this only says
 * so. One component for prices, restricted data and support-grant exclusions.
 *
 * The cell takes focus, so the sentence is reachable by keyboard and tap as
 * well as by hover (WCAG 1.4.13); Esc closes the tooltip (antd).
 */
export function MaskedValue({ sentence }: MaskedValueProps) {
  return (
    <Tooltip title={sentence}>
      <span
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        role="img"
        aria-label={`${MASKED_LABEL}. ${sentence}`}
        className="inline-flex items-center gap-1 whitespace-nowrap"
        data-masked="true"
      >
        <LockOutlined aria-hidden />
        {MASKED_LABEL}
      </span>
    </Tooltip>
  );
}

/**
 * The same lock for a whole region (a table of other customers' prices, an
 * evidence panel): the sentence written out once, in place of the content.
 */
export function MaskedRegion({ sentence }: MaskedValueProps) {
  return (
    <Alert
      type="info"
      showIcon
      icon={<LockOutlined />}
      title={MASKED_LABEL}
      description={sentence}
      data-masked="true"
    />
  );
}
