/**
 * The one place a date is turned into text for the screen.
 *
 * The app renders one date shape everywhere: DD/MM/YYYY, with a 24-hour clock
 * when the time matters. Written out rather than left to `Intl` because the
 * order, the separator and the clock are the requirement, not a locale
 * preference — `toLocaleString` prints US short forms on a US-locale browser
 * and the screens would disagree with each other.
 */

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** "DD/MM/YYYY", or an em dash when there is no date. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}

/** "DD/MM/YYYY HH:mm", or an em dash when there is no date. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return `${formatDate(iso)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
