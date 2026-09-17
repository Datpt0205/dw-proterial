import type { LabelHTMLAttributes } from "react";
import { cn } from "./cn";

/**
 * A form label. Thin on purpose: what it adds over a bare `<label>` is one
 * consistent type scale and the disabled treatment, so a screen full of fields
 * does not drift into three sizes of caption.
 *
 * It does NOT generate an id or wire itself to a control. `htmlFor` is the
 * caller's, because a label that guesses which input it belongs to is a label
 * that eventually points at the wrong one.
 */
export function Label({
  className,
  ...props
}: LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "text-sm font-medium leading-none text-foreground peer-disabled:cursor-not-allowed peer-disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
