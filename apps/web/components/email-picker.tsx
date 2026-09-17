"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@dw/ui";

export interface EmailOption {
  email: string;
  display_name: string;
}

/**
 * A combobox over signed-in accounts. Deliberately NOT a native <datalist>:
 * that merges the browser's own saved-address autofill into the list, which
 * looks like the app is suggesting random personal emails. This shows only the
 * accounts we pass, and `autoComplete="off"` keeps the browser out. Still fully
 * typeable — a not-yet-seen email can be entered by hand.
 */
export function EmailPicker({
  value,
  onChange,
  options,
  placeholder,
  className,
  onOpen,
}: {
  value: string;
  onChange: (value: string) => void;
  options: EmailOption[];
  placeholder?: string;
  className?: string;
  /** Called when the field is focused, so the caller can refresh its options
   *  (e.g. re-fetch people who signed in since the page loaded). */
  onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const q = value.trim().toLowerCase();
  const matches = options
    .filter(
      (o) =>
        !q ||
        o.email.toLowerCase().includes(q) ||
        o.display_name.toLowerCase().includes(q),
    )
    .slice(0, 8);

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          onOpen?.();
        }}
        className={cn(
          "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-60 w-full min-w-[16rem] overflow-auto rounded-md border bg-card shadow-lg">
          {matches.map((o) => (
            <li key={o.email}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange(o.email);
                  setOpen(false);
                }}
                className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-muted"
              >
                <span className="text-sm font-medium">{o.email}</span>
                <span className="text-xs text-muted-foreground">
                  {o.display_name}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
