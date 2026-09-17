"use client";

/**
 * The country picker, ported from the previous system's combobox.
 *
 * A real combobox rather than a `<datalist>`, which is what it replaced there:
 * a datalist shows nothing until you type, highlights nothing, and cannot be
 * styled, so nobody could tell how many countries were on offer.
 *
 * The panel is portalled to `<body>`, and that is not a detail. Every caller is
 * a scrolling modal, and an absolutely-positioned panel inside one is clipped at
 * its edge. Coordinates are `fixed`, taken from the input's bounding rect,
 * flipped upward when there is no room below, and the panel closes on scroll
 * rather than following - a fixed position is captured once, so following would
 * mean drifting off the field.
 *
 * Contract: `value` is the lowercase ISO-2 code and `onChange` returns one. The
 * input only ever displays the label. Controlled properly - the query is state
 * of its own - so a `value` changed from outside shows immediately, with none of
 * the remount-by-changing-key trick the earlier version needed.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { ChevronDown } from "lucide-react";
import { cn } from "@dw/ui";
import { COUNTRIES, labelOf } from "../lib/countries";

const MAX_PANEL_HEIGHT = 260;
const GAP = 4;

/** Fold accents and case so "turkiye" matches "Turkiye" and "viet" Vietnam. */
function fold(value: string): string {
  // \u0300-\u036f is the combining-marks block. Written as escapes and
  // never pasted: a bare combining mark in source gets swallowed by editors,
  // diffs and formatters, and it fails silently - the filter simply stops
  // matching accented names.
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function CountrySelect({
  value,
  onChange,
  disabled = false,
  placeholder = "Search countries…",
  className = "",
}: {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const [position, setPosition] = useState<{
    top: number;
    left: number;
    width: number;
    flip: boolean;
  }>();
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const label = labelOf(value);

  // Matched on the label and on the code, so typing "vn" also finds Vietnam.
  const items = useMemo(() => {
    const needle = fold(query.trim());
    if (!needle) return COUNTRIES;
    return COUNTRIES.filter(
      (country) =>
        fold(country.label).includes(needle) || country.code.includes(needle),
    );
  }, [query]);

  const place = useCallback(() => {
    const element = inputRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const flip =
      rect.bottom + MAX_PANEL_HEIGHT > window.innerHeight &&
      rect.top > MAX_PANEL_HEIGHT;
    setPosition({
      top: flip ? rect.top - GAP : rect.bottom + GAP,
      left: rect.left,
      width: rect.width,
      flip,
    });
  }, []);

  const show = useCallback(() => {
    if (disabled) return;
    place();
    // Already open: reposition only. The query must not be cleared here - the
    // input takes click and focus while it is being typed into, and clobbering
    // it there wipes what somebody just typed.
    if (open) return;
    setQuery("");
    // Open with the cursor on the country already chosen, not the first row.
    setHighlighted(
      Math.max(
        0,
        COUNTRIES.findIndex((country) => country.code === value),
      ),
    );
    setOpen(true);
  }, [disabled, open, place, value]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  const pick = (code: string) => {
    onChange(code);
    close();
    inputRef.current?.blur();
  };

  useEffect(() => {
    if (!open) return;
    const onAway = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        inputRef.current?.contains(target) ||
        panelRef.current?.contains(target)
      )
        return;
      close();
    };
    // The panel scrolls too - sixty-odd countries in 260px - so listening for
    // `scroll` in the capture phase catches scrolling *inside* it as well, and
    // the picker closes the instant it opens: the effect below pulls the chosen
    // row into view, and the default "vn" is last in the list.
    const onScroll = (event: Event) => {
      if (panelRef.current?.contains(event.target as Node)) return;
      close();
    };
    document.addEventListener("mousedown", onAway);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onAway);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open, close]);

  useEffect(() => {
    if (!open) return;
    panelRef.current
      ?.querySelector<HTMLElement>('[data-highlighted="1"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [highlighted, open]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) {
      if (event.key === "ArrowDown" || event.key === "Enter") {
        event.preventDefault();
        show();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => Math.min(index + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const chosen = items[highlighted];
      if (chosen) pick(chosen.code);
    } else if (event.key === "Escape" || event.key === "Tab") {
      // Neither selects: the held code stays and the field snaps back to it.
      close();
    }
  };

  return (
    <>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && items[highlighted]
              ? `${listId}-${items[highlighted].code}`
              : undefined
          }
          autoComplete="off"
          disabled={disabled}
          // Closed, it shows the label of the code it holds. Open, it shows what
          // is being typed and the old label falls back to the placeholder, so
          // the context is not lost mid-search.
          value={open ? query : label}
          placeholder={open ? label || placeholder : placeholder}
          onChange={(event) => {
            setQuery(event.target.value);
            setHighlighted(0);
            if (!open) show();
          }}
          onFocus={show}
          onClick={show}
          onKeyDown={onKeyDown}
          className={cn(
            "w-full rounded-md border bg-background py-1.5 pl-2.5 pr-6 text-sm",
            className,
          )}
        />
        <ChevronDown
          className="pointer-events-none absolute right-1.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
      </div>

      {open && position && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={panelRef}
              id={listId}
              role="listbox"
              style={{
                position: "fixed",
                top: position.top,
                left: position.left,
                width: Math.max(position.width, 180),
                maxHeight: MAX_PANEL_HEIGHT,
                transform: position.flip ? "translateY(-100%)" : undefined,
                zIndex: 90,
              }}
              className="overflow-y-auto rounded-lg border bg-card py-1 shadow-lg"
            >
              {items.length === 0 ? (
                <p className="px-2.5 py-1.5 text-sm text-muted-foreground">
                  No countries match.
                </p>
              ) : null}
              {items.map((country, index) => (
                <button
                  key={country.code}
                  id={`${listId}-${country.code}`}
                  type="button"
                  role="option"
                  aria-selected={country.code === value}
                  data-highlighted={index === highlighted ? "1" : undefined}
                  // mousedown, not click: click fires after the input's blur,
                  // and blur may already have closed the panel - which loses
                  // the selection entirely.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    pick(country.code);
                  }}
                  onMouseEnter={() => setHighlighted(index)}
                  className={cn(
                    "flex w-full items-center justify-between px-2.5 py-1.5 text-left text-sm",
                    index === highlighted
                      ? "bg-sky-50 text-sky-700"
                      : "text-foreground",
                    country.code === value ? "font-medium" : "",
                  )}
                >
                  <span>{country.label}</span>
                  <span className="text-[11px] uppercase text-muted-foreground">
                    {country.code}
                  </span>
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
