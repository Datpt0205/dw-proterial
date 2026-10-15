"use client";

import { useEffect, useState } from "react";
import { serverNow } from "./server-clock";

/**
 * The time a relative label ("còn 2 ngày 4 giờ") is computed against, ticking
 * every `intervalMs` so a page left open overnight keeps counting and changes
 * state when a deadline passes (ui-quality §8).
 *
 * It is the server's clock (`lib/server-clock.ts`, read off the API's
 * responses), so a device whose clock is wrong still shows the right "còn".
 */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(serverNow);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(serverNow()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
