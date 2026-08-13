import type { ReactNode } from "react";

/**
 * Shared chart shell: title, unit, legend, empty state, and the data table
 * that sits behind every chart.
 *
 * The table is not optional decoration -- it is the accessible path to exact
 * values and the reason these charts do not rely on hover alone.
 */
export function ChartFrame({
  title,
  unit,
  summary,
  legend,
  isEmpty,
  emptyMessage = "No data in range.",
  table,
  children,
}: {
  title: string;
  /** What the axis measures, e.g. "wins per season". */
  unit: string;
  /** One-sentence description of the trend, read out to screen readers. */
  summary: string;
  legend?: { label: string; color: string }[];
  isEmpty: boolean;
  emptyMessage?: string;
  table: ReactNode;
  children: ReactNode;
}) {
  return (
    <figure className="chart" style={{ margin: 0 }}>
      <div className="chart__head">
        <h3 className="chart__title">{title}</h3>
        <span className="chart__unit mono">{unit.toUpperCase()}</span>
      </div>
      {isEmpty ? (
        <p style={{ color: "var(--text-dim)", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
          {emptyMessage}
        </p>
      ) : (
        <>
          <div role="img" aria-label={summary}>
            {children}
          </div>
          {legend && (
            <div className="chart__legend">
              {legend.map((item) => (
                <span key={item.label}>
                  <span className="chart__swatch" style={{ background: item.color }} />
                  {item.label}
                </span>
              ))}
            </div>
          )}
          <details className="chart__table">
            <summary>Show data table</summary>
            {table}
          </details>
        </>
      )}
    </figure>
  );
}

/* Kept as re-exports so existing chart imports keep working; the values
   themselves now live in palette.ts and point at design tokens. */
export { AXIS, TICK } from "./palette";

/** Evenly spaced, human-round tick values for a 0..max axis. */
export function ticks(max: number, count = 4): number[] {
  if (max <= 0) return [0];
  const step = Math.max(1, Math.ceil(max / count));
  const out: number[] = [];
  for (let value = 0; value <= max; value += step) out.push(value);
  return out;
}

/** Thin out x labels so they never collide on narrow viewports. */
export function labelEvery(count: number, budget = 12): number {
  return Math.max(1, Math.ceil(count / budget));
}
