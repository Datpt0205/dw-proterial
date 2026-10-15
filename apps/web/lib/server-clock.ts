/**
 * The server's clock, as the API's responses tell it (their `Date` header,
 * which the API exposes to the browser for this). A relative label ("còn 2
 * ngày 4 giờ") is counted against it, not against this device, whose clock
 * may be minutes or hours off (ui-quality §8): the deadline is the server's,
 * so the "now" it is compared with is too.
 *
 * Only the offset is kept, so the time still moves between responses. Until
 * a response has said otherwise the offset is zero: the device's clock.
 */
let offsetMs = 0;

/** Read the server's clock off one response's `Date` header. */
export function noteServerDate(header: string | null): void {
  if (!header) return;
  const at = Date.parse(header);
  if (!Number.isFinite(at)) return;
  // `Date` has whole seconds and is cut, not rounded: the server's clock was
  // somewhere in the second it names, so take its middle.
  offsetMs = at + 500 - Date.now();
}

/** Now, by the server's clock. */
export function serverNow(): number {
  return Date.now() + offsetMs;
}
