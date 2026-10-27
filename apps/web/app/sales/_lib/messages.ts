/**
 * How a message is named on screen (ticket 43). A mail stored from the drop
 * folder has its file's sha256 as its id, "eml-" and 64 hex digits, which
 * no one reads and no row has room for: it is shown by its first 8 digits,
 * enough to tell one mail from another on a screen and when talking to
 * support. Links and requests keep the whole id. A mock message's id ("M01")
 * is shown as it is.
 */
export function messageRef(messageId: string): string {
  const stored = /^eml-([0-9a-f]{64})$/.exec(messageId);
  return stored ? `eml-${stored[1]!.slice(0, 8)}` : messageId;
}
