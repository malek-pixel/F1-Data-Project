/** Presentation-only formatting. No calculation happens here -- if a number
 *  needs deriving, it is derived in backend/app/analytics.py. */

const DASH = "—";

/** Locale-aware integer. */
export function num(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : value.toLocaleString();
}

/** Rate as a percentage. null (no entries) renders as an em dash, never "0%". */
export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? DASH : `${(value * 100).toFixed(digits)}%`;
}

/** Fixed-precision decimal, e.g. average classified position. */
export function dec(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? DASH : value.toFixed(digits);
}

/** Locale-aware date, forced to UTC so a race never shifts a day by timezone. */
export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, {
    timeZone: "UTC",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Season span for a list of seasons, e.g. "2007–2025". */
export function seasonSpan(seasons: number[]): string {
  if (seasons.length === 0) return DASH;
  const lo = Math.min(...seasons);
  const hi = Math.max(...seasons);
  return lo === hi ? `${lo}` : `${lo}–${hi}`;
}
