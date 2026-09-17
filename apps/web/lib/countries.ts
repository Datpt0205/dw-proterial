/**
 * The countries the account picker offers, ported from the previous system.
 *
 * Codes are lowercase ISO 3166-1 alpha-2, matching `accounts.country` and the
 * keys of the market registry in `domain/shared/countries.py`.
 *
 * NOT an allowlist: the API takes any two-letter code. A country the registry
 * declares (`vn`, `jp`, `us`) gets its own search languages, fiscal year and
 * anchor sources; anything else falls back to the global rules and research
 * records a note saying it did. Adding a row here needs no backend change.
 */
export const DEFAULT_COUNTRY = "vn";

export const COUNTRIES: { code: string; label: string }[] = [
  { code: "ar", label: "Argentina" },
  { code: "au", label: "Australia" },
  { code: "at", label: "Austria" },
  { code: "bh", label: "Bahrain" },
  { code: "bd", label: "Bangladesh" },
  { code: "be", label: "Belgium" },
  { code: "br", label: "Brazil" },
  { code: "bn", label: "Brunei" },
  { code: "bg", label: "Bulgaria" },
  { code: "kh", label: "Cambodia" },
  { code: "ca", label: "Canada" },
  { code: "cl", label: "Chile" },
  { code: "cn", label: "China" },
  { code: "co", label: "Colombia" },
  { code: "cr", label: "Costa Rica" },
  { code: "cz", label: "Czechia" },
  { code: "dk", label: "Denmark" },
  { code: "eg", label: "Egypt" },
  { code: "fi", label: "Finland" },
  { code: "fr", label: "France" },
  { code: "de", label: "Germany" },
  { code: "hk", label: "Hong Kong SAR China" },
  { code: "hu", label: "Hungary" },
  { code: "in", label: "India" },
  { code: "id", label: "Indonesia" },
  { code: "ie", label: "Ireland" },
  { code: "il", label: "Israel" },
  { code: "it", label: "Italy" },
  { code: "jp", label: "Japan" },
  { code: "kz", label: "Kazakhstan" },
  { code: "kw", label: "Kuwait" },
  { code: "la", label: "Laos" },
  { code: "lu", label: "Luxembourg" },
  { code: "my", label: "Malaysia" },
  { code: "mx", label: "Mexico" },
  { code: "mm", label: "Myanmar (Burma)" },
  { code: "nl", label: "Netherlands" },
  { code: "nz", label: "New Zealand" },
  { code: "ng", label: "Nigeria" },
  { code: "no", label: "Norway" },
  { code: "om", label: "Oman" },
  { code: "pk", label: "Pakistan" },
  { code: "pe", label: "Peru" },
  { code: "ph", label: "Philippines" },
  { code: "pl", label: "Poland" },
  { code: "pt", label: "Portugal" },
  { code: "qa", label: "Qatar" },
  { code: "ro", label: "Romania" },
  { code: "sa", label: "Saudi Arabia" },
  { code: "sg", label: "Singapore" },
  { code: "sk", label: "Slovakia" },
  { code: "za", label: "South Africa" },
  { code: "kr", label: "South Korea" },
  { code: "es", label: "Spain" },
  { code: "lk", label: "Sri Lanka" },
  { code: "se", label: "Sweden" },
  { code: "ch", label: "Switzerland" },
  { code: "tw", label: "Taiwan" },
  { code: "th", label: "Thailand" },
  { code: "tr", label: "Türkiye" },
  { code: "ae", label: "United Arab Emirates" },
  { code: "gb", label: "United Kingdom" },
  { code: "us", label: "United States" },
  { code: "vn", label: "Vietnam" },
];

/**
 * The label for a code.
 *
 * An unlisted code returns itself upper-cased rather than an empty string: the
 * API accepts codes this list has not caught up with, and showing "BR" beats
 * showing nothing and reading as "no country set".
 */
export function labelOf(code: string | null | undefined): string {
  const c = (code || "").trim().toLowerCase();
  if (!c) return "";
  return COUNTRIES.find((x) => x.code === c)?.label ?? c.toUpperCase();
}
