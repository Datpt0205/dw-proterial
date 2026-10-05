"use client";

import { useEffect, useState } from "react";

/**
 * The time a relative label ("còn 2 ngày 4 giờ") is computed against, ticking
 * every `intervalMs` so a page left open overnight keeps counting and changes
 * state when a deadline passes (ui-quality §8).
 *
 * It is this device's clock. The API sends no server time on the reads these
 * labels sit beside, so a device whose clock is wrong shows a wrong "còn";
 * the absolute time next to it, from the server's value, stays right.
 */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
