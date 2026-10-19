/**
 * The placeholders of a template field (ticket 40), as the editor lists them.
 *
 * Two syntaxes, as the readers fill them: the e-mail and document copy is
 * `string.Template` (`${po_no}`, `artifact_content.fill`), and the hand-off
 * copy is `str.format` with bare names only (`{customer}`,
 * `handoffs._plain_placeholders`). The hand-off schema lists the names its
 * validator allows (`x-placeholders`); the e-mail and document schemas do
 * not, because which values a draft has is decided by the code that draws
 * it, kind by kind. For those the editor shows what the version in force
 * uses in the same field: a hint, not a rule, which is why it only warns.
 *
 * No preview is drawn: the filling code is Python and no endpoint renders a
 * template with a sample case.
 */
export type Syntax = "dollar" | "braces";

/** `${name}` placeholders in a `string.Template` text, each once, in order. */
export function placeholdersIn(text: string): string[] {
  const found = [...text.matchAll(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g)].map(
    (m) => `\${${m[1] ?? m[2]}}`,
  );
  return [...new Set(found)];
}

/** `{name}` fields of a `str.format` text, as written (`{customer:>9}` whole). */
function formatFields(text: string): string[] {
  // "{{" and "}}" are literal braces in str.format.
  const plain = text.replace(/\{\{|\}\}/g, "");
  return [...plain.matchAll(/\{([^{}]*)\}/g)].map((m) => `{${m[1]}}`);
}

/** The placeholders in `text` that `allowed` does not list. */
export function unknownPlaceholders(
  text: string,
  allowed: readonly string[],
  syntax: Syntax,
): string[] {
  const used = syntax === "braces" ? formatFields(text) : placeholdersIn(text);
  const known = new Set(allowed);
  return [...new Set(used.filter((name) => !known.has(name)))];
}
