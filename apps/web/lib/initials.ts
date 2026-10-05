/** "Nguyễn Văn An" → "NA": the first and the last word's initials, for an avatar. */
export function initials(name: string): string {
  // Words that start with a letter: "(bạn)" or "(PIC)" make no initial.
  const words = name
    .trim()
    .split(/\s+/)
    .filter((word) => /^\p{L}/u.test(word));
  if (words.length === 0) return "?";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : "";
  return (first + last).toUpperCase();
}
