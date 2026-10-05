/**
 * The one place a list's text search and text sort are decided
 * (ui-quality §8): "ha noi" finds "Hà Nội" and "d" finds "đ", and a sort by a
 * Vietnamese name puts "Đ" after "D", never after "Z".
 */

/** `text` without its marks, "đ" as "d", in lower case: what a search compares. */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[đĐ]/g, "d")
    .toLowerCase();
}

/**
 * Whether every word of `query` is in one of `fields`, marks and case
 * ignored. An empty query matches everything.
 */
export function matches(
  query: string,
  fields: readonly (string | null | undefined)[],
): boolean {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fold(fields.filter(Boolean).join(" "));
  return words.every((word) => haystack.includes(word));
}

const collator = new Intl.Collator("vi", {
  sensitivity: "base",
  numeric: true,
});

/** Compares two texts the way a Vietnamese reader orders them. */
export function compareVi(
  a: string | null | undefined,
  b: string | null | undefined,
): number {
  return collator.compare(a ?? "", b ?? "");
}
