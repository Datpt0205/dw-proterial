"use client";

import { useId } from "react";
import { Button, Tooltip, Typography, type ButtonProps } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";

/**
 * A button that may be refused, saying why in words (ui-quality §5): the
 * reason in a `Tooltip`, always, and, because a disabled button takes no
 * focus and shows nothing on tap, the same sentence written beside it. The
 * server refuses the same step whatever this button shows.
 */
export function GuardedButton({
  reason,
  inlineReason = true,
  children,
  ...props
}: ButtonProps & {
  /** Why the step cannot be taken now; null when it can. */
  reason: string | null;
  /** Write the reason beside the button as well as in the tooltip. */
  inlineReason?: boolean;
}) {
  const id = useId();
  if (!reason) return <Button {...props}>{children}</Button>;
  return (
    <span className="inline-flex max-w-full flex-col items-start gap-1">
      <Tooltip title={reason}>
        <Button
          {...props}
          disabled
          aria-describedby={inlineReason ? id : undefined}
        >
          {children}
        </Button>
      </Tooltip>
      {inlineReason ? (
        <Typography.Text id={id} className="max-w-md" role="note">
          <InfoCircleOutlined aria-hidden className="me-1" />
          {reason}
        </Typography.Text>
      ) : null}
    </span>
  );
}
