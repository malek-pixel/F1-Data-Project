import type { DriverContribution } from "../types";
import { num, pct } from "../components/format";
import { ChartFrame } from "./Chart";

/** Categorical series colours. Chosen for contrast against the dark surface
 *  and distinguishable in the common forms of colour blindness -- and every
 *  segment is labelled in the data table regardless. */
const SERIES = ["#e10600", "#0090ff", "#22c55e", "#f59e0b", "#a78bfa", "#14b8a6", "#f472b6", "#94a3b8"];

/**
 * Driver contribution within a constructor, as a stacked proportion bar.
 *
 * Stacked bars are the right form here because the parts genuinely sum to a
 * meaningful whole (this team's entries / wins / podiums).
 *
 * Note this is share of *results*, not share of points -- the source has no
 * points column. The caption says so, because "contribution" would otherwise
 * be read as points.
 */
export function DriverContributionChart({
  rows,
  metric,
}: {
  rows: DriverContribution[];
  metric: "entry_share" | "win_share" | "podium_share";
}) {
  const label = { entry_share: "entries", win_share: "wins", podium_share: "podiums" }[metric];
  const counted = { entry_share: "entries", win_share: "wins", podium_share: "podiums" } as const;
  const present = rows.filter((row) => (row[metric] ?? 0) > 0);
  const total = present.reduce((sum, row) => sum + (row[metric] ?? 0), 0);

  let offset = 0;
  const segments = present.map((row, index) => {
    const width = ((row[metric] ?? 0) / total) * 100;
    const segment = { row, width, offset, color: SERIES[index % SERIES.length] };
    offset += width;
    return segment;
  });

  return (
    <ChartFrame
      title={`Driver contribution — share of ${label}`}
      unit={`share of team ${label} · not points`}
      summary={
        segments.length
          ? `Share of team ${label} by driver. Largest contributor: ${segments[0].row.driver_name} at ${pct(segments[0].row[metric])}.`
          : `This constructor recorded no ${label}.`
      }
      isEmpty={segments.length === 0}
      emptyMessage={`This constructor recorded no ${label} in the dataset.`}
      legend={segments.map((s) => ({ label: s.row.driver_name, color: s.color }))}
      table={
        <div className="table-scroll">
          <table className="data">
            <caption style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
              {`Driver share of team ${label}`}
            </caption>
            <thead>
              <tr>
                <th scope="col">Driver</th>
                <th scope="col" className="num">{label[0].toUpperCase() + label.slice(1)}</th>
                <th scope="col" className="num">Share</th>
              </tr>
            </thead>
            <tbody>
              {present.map((row) => (
                <tr key={row.driver_id}>
                  <td>{row.driver_name}</td>
                  <td className="num">{num(row[counted[metric]])}</td>
                  <td className="num">{pct(row[metric])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    >
      <svg viewBox="0 0 760 56" preserveAspectRatio="none" style={{ height: 56 }}>
        {segments.map((segment) => (
          <rect
            key={segment.row.driver_id}
            x={`${segment.offset}%`}
            y="8"
            width={`${segment.width}%`}
            height="32"
            fill={segment.color}
          >
            <title>
              {`${segment.row.driver_name}: ${num(segment.row[counted[metric]])} ${label} (${pct(segment.row[metric])})`}
            </title>
          </rect>
        ))}
      </svg>
    </ChartFrame>
  );
}

/**
 * Head-to-head bars: one metric, two entities, mirrored around a shared axis.
 * Values are printed on both sides, so the comparison never depends on
 * judging bar length by eye.
 */
export function ComparisonBar({
  label,
  leftLabel,
  rightLabel,
  left,
  right,
  format,
  lowerIsBetter,
}: {
  label: string;
  leftLabel: string;
  rightLabel: string;
  left: number | null;
  right: number | null;
  format: (value: number | null) => string;
  lowerIsBetter?: boolean;
}) {
  const max = Math.max(left ?? 0, right ?? 0) || 1;
  const leftPct = ((left ?? 0) / max) * 100;
  const rightPct = ((right ?? 0) / max) * 100;

  // Only mark a leader when both sides have a value; a missing value is not a loss.
  const leader =
    left === null || right === null
      ? null
      : lowerIsBetter
        ? left < right ? "left" : right < left ? "right" : null
        : left > right ? "left" : right > left ? "right" : null;

  return (
    <div style={{ display: "grid", gap: 6, marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <span className="mono" style={{ fontSize: 13, fontWeight: leader === "left" ? 600 : 400 }}>
          {format(left)}
          {leader === "left" && <span aria-label=" (leads)"> ◂</span>}
        </span>
        <span className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)" }}>
          {label}
        </span>
        <span className="mono" style={{ fontSize: 13, fontWeight: leader === "right" ? 600 : 400 }}>
          {leader === "right" && <span aria-label="(leads) "> ▸</span>}
          {format(right)}
        </span>
      </div>
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        <div style={{ flex: 1, height: 8, display: "flex", justifyContent: "flex-end" }}>
          <div
            style={{ width: `${leftPct}%`, background: "var(--accent)", borderRadius: "3px 0 0 3px" }}
            role="img"
            aria-label={`${leftLabel}: ${format(left)}`}
          />
        </div>
        <div style={{ flex: 1, height: 8 }}>
          <div
            style={{ width: `${rightPct}%`, background: "var(--info)", borderRadius: "0 3px 3px 0" }}
            role="img"
            aria-label={`${rightLabel}: ${format(right)}`}
          />
        </div>
      </div>
    </div>
  );
}
