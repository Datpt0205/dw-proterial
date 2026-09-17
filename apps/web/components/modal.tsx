"use client";

import { X } from "lucide-react";
import { Dialog } from "radix-ui";
import { cn } from "@dw/ui";

/** Lightweight modal/dialog, built on Radix Dialog.
 *
 * Radix owns the behaviour we used to hand-roll: Escape to close, a focus trap,
 * body-scroll lock, and — crucially — closing only when the press BEGAN outside
 * the dialog. Selecting text inside a field and releasing the mouse past the
 * edge no longer closes it (Radix's `onPointerDownOutside`), which was the bug
 * the hand-written backdrop handler kept reintroducing. The public API is
 * unchanged, so callers stay the same. */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  className,
  headerActions,
  footerActions,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  /** Buttons that belong in the header's right corner (spec 003 US6: the
   * create-lead form keeps Cancel/Create in view without scrolling). */
  headerActions?: React.ReactNode;
  /** Buttons pinned below the scroll area — always in view however long the
   * body grows (the create-account form keeps Cancel/Create here). */
  footerActions?: React.ReactNode;
}) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/35 backdrop-blur-[2px]" />
        {/* A positioning layer over the overlay: it keeps the mobile bottom-sheet
            / desktop-centered layout the app had. A press that starts here (not
            on the dialog) is an outside press, so Radix closes. */}
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-0 sm:p-8">
          <Dialog.Content
            aria-describedby={undefined}
            className={cn(
              // A flex column capped to the viewport: the header and footer are
              // pinned, and ONLY the body scrolls — long content must never push
              // the action buttons off screen (user rule 2026-08-28).
              "relative mt-auto flex max-h-dvh w-full max-w-2xl flex-col rounded-t-3xl border bg-background shadow-2xl focus:outline-none sm:my-auto sm:max-h-[calc(100dvh-4rem)] sm:rounded-2xl",
              className,
            )}
          >
            <div className="flex shrink-0 items-start justify-between gap-3 border-b bg-slate-50/70 p-5 sm:rounded-t-2xl">
              <div className="min-w-0">
                <Dialog.Title className="truncate text-base font-semibold">
                  {title}
                </Dialog.Title>
                {subtitle && (
                  <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                    {subtitle}
                  </Dialog.Description>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {headerActions}
                <Dialog.Close
                  className="rounded-md p-1 text-muted-foreground transition hover:bg-muted hover:text-foreground"
                  aria-label="Close"
                >
                  <X className="size-5" />
                </Dialog.Close>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
              {children}
            </div>
            {footerActions && (
              <div className="flex shrink-0 items-center justify-end gap-2 border-t bg-slate-50/70 p-4 sm:rounded-b-2xl">
                {footerActions}
              </div>
            )}
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
