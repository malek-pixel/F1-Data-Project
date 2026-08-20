/**
 * The one categorical palette.
 *
 * Three near-copies of this list had drifted apart -- Home and the season page
 * used #A855F7/#EC4899 for slots 5 and 7, the contribution chart used
 * #a78bfa/#f472b6 -- so the same constructor changed colour depending on which
 * screen you were looking at. A shared series is what makes "purple is the
 * fourth-ranked team" hold across the app.
 *
 * Assigned by rank within the selected season, never from a table of team
 * liveries: the dataset spans 2000-2025, teams change owner and colour, and
 * several no longer exist. A positional palette stays legible without
 * asserting a brand identity the data does not carry.
 *
 * Hues are spaced far enough apart to survive the common colour-vision
 * deficiencies, and every chart that uses them also ships a legend and a data
 * table, so colour is never the only carrier of meaning.
 */
export const SERIES = [
  "#e10600", // accent red
  "#0090ff", // info blue
  "#f59e0b", // amber
  "#22c55e", // green
  "#a855f7", // violet
  "#14b8a6", // teal
  "#ec4899", // pink
  "#94a3b8", // slate
];

/** Colour for `name`'s position in `order`, falling back to a neutral. */
export function seriesColour(name: string | null, order: string[]): string {
  if (!name) return "var(--border)";
  const index = order.indexOf(name);
  return index === -1 ? "var(--text-faint)" : SERIES[index % SERIES.length];
}

/* Chart furniture, as tokens rather than literals.
   These were hardcoded hexes, and the tick colour had gone stale: it was
   #6f7a89, the exact value tokens.css rejects for measuring 4.17:1 against
   --surface, below the 4.5:1 the app's own header claims. Pointing at the
   token means the correction applies here too, and cannot drift again. */
export const AXIS = "var(--border)";
/**
 * Gridlines, deliberately lighter than the axis.
 *
 * Both were drawn with AXIS, so a horizontal gridline had exactly the weight
 * of the baseline it sat above -- the plot read as a stack of equal rules with
 * the data drawn over it, rather than as marks against a reference. Grid
 * furniture must sit behind the data it measures.
 */
export const GRID = "var(--line)";
export const TICK = "var(--text-faint)";
export const LABEL = "var(--text-dim)";
