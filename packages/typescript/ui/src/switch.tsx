import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

/**
 * A native checkbox drawn as a switch.
 *
 * Native rather than a headless-library toggle, and the reason is the keyboard:
 * `<input type="checkbox">` already answers Space, already announces its
 * checked state to a screen reader, and already pairs with a `<label htmlFor>`.
 * A div with `role="switch"` has to be taught all three, and usually is taught
 * two of them.
 *
 * The input is transparent and covers the whole control rather than being
 * clipped away with `sr-only`. That is the difference between a switch a mouse
 * can operate and one it cannot: with `sr-only` the input is a clipped box the
 * painted track sits on top of, so every pointer event lands on a decorative
 * `aria-hidden` span and nothing toggles. Keyboard users would never have
 * noticed; a browser test did.
 *
 * Transparent rather than hidden keeps focus, tab order, form submission and
 * the accessible name exactly as they are for any checkbox — the track and the
 * knob are painted behind it, driven by `peer-checked` and
 * `peer-focus-visible`.
 */
export type SwitchProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function Switch({ className, ...props }: SwitchProps) {
  return (
    <span
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center",
        className,
      )}
    >
      <input
        type="checkbox"
        className="peer absolute inset-0 z-10 m-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        {...props}
      />
      <span
        aria-hidden
        className="pointer-events-none h-5 w-9 rounded-full bg-muted-foreground/30 transition-colors peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-primary/30 peer-focus-visible:ring-offset-2 peer-disabled:opacity-50"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform peer-checked:translate-x-4"
      />
    </span>
  );
}
