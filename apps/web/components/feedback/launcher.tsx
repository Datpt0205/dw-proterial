"use client";

import { useState } from "react";
import { Button, FloatButton, Tooltip } from "antd";
import { MessageOutlined } from "@ant-design/icons";
import { FeedbackDialog } from "./dialog";

const LABEL = "Gửi phản hồi";

/**
 * The feedback entry point (spec 003 US5). Not a nav item on purpose:
 * feedback is a utility beside the app, not a module of it, and always in
 * view, so a person reports a bug from the page it happened on.
 *
 * - `float`, from `md` up: a round button pinned to the bottom-left corner;
 *   the shell keeps room under the page for it (`AppFrame`).
 * - `bar`, below `md`: an icon button among the top bar's actions. Floating
 *   on a phone it covered what pages put first (the O6 chip, a table's first
 *   columns: screenshot review of 2026-10-21, browser look of 2026-10-24),
 *   and no padding stops a fixed button covering what scrolls under it.
 */
export function FeedbackLauncher({
  placement,
}: {
  placement: "float" | "bar";
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {placement === "float" ? (
        <FloatButton
          type="primary"
          icon={<MessageOutlined aria-hidden />}
          aria-label={LABEL}
          tooltip={LABEL}
          onClick={() => setOpen(true)}
          style={{ insetInlineStart: 20, insetInlineEnd: "auto", bottom: 20 }}
        />
      ) : (
        <Tooltip title={LABEL}>
          <Button
            type="text"
            icon={<MessageOutlined aria-hidden />}
            aria-label={LABEL}
            onClick={() => setOpen(true)}
          />
        </Tooltip>
      )}
      {open && <FeedbackDialog onClose={() => setOpen(false)} />}
    </>
  );
}
