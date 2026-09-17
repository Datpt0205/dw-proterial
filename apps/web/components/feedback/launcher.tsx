"use client";

import { useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import { FeedbackDialog } from "./dialog";

/**
 * The feedback entry point (spec 003 US5): a round button pinned to the
 * bottom-left corner of every signed-in page. Not a nav item on purpose —
 * feedback is a utility beside the app, not a module of it — and always in
 * view, so a person reports a bug from the page it happened on.
 */
export function FeedbackLauncher() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-label="Feedback"
        title="Gửi phản hồi"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 left-5 z-40 flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/30 transition hover:scale-105 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <MessageSquarePlus className="size-5" />
      </button>
      {open && <FeedbackDialog onClose={() => setOpen(false)} />}
    </>
  );
}
