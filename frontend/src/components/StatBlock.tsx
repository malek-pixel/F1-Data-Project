import type { Stats } from "../types";
import { dec, num, pct } from "./format";
import { StatCard, Badge } from "./ui";
import { Unavailable } from "./States";

/**
 * The canonical KPI row for a driver, constructor or circuit.
 *
 * Two rules this component exists to enforce:
 *
 *  1. "Average classified position" is labelled exactly that -- never
 *     "average finish". The source has no status column, so retirements are
 *     ranked, not excluded.
 *  2. Rates flagged `rates_reliable: false` are shown with a visible sample
 *     caveat rather than hidden, so a small sample is obvious instead of absent.
 */
export function StatBlock({ stats, entryNoun = "entries" }: { stats: Stats; entryNoun?: string }) {
  const caveat = stats.rates_reliable ? undefined : `Small sample (${stats.entries} ${entryNoun})`;
  return (
    <div className="grid grid--kpi">
      <StatCard label="ENTRIES" value={num(stats.entries)} note="Classifications, incl. retirements" />
      <StatCard label="WINS" value={num(stats.wins)} />
      <StatCard label="PODIUMS" value={num(stats.podiums)} note="Classified P1–P3" />
      <StatCard label="WIN RATE" value={pct(stats.win_rate)} note={caveat ?? "wins / entries"} tone={caveat ? "warning" : undefined} />
      <StatCard label="PODIUM RATE" value={pct(stats.podium_rate)} note={caveat ?? "podiums / entries"} tone={caveat ? "warning" : undefined} />
      <StatCard
        label="AVG CLASSIFIED POS"
        value={dec(stats.avg_classified_position)}
        note="Mean classification, incl. retirements"
      />
      <StatCard
        label="TOP-10 RATE"
        value={pct(stats.top10_rate)}
        note={caveat ?? `${num(stats.top10)} of ${num(stats.entries)} entries`}
        tone={caveat ? "warning" : undefined}
      />
      {/* "Best classified position", not "best finish": the field is
          min(position), and position is classification order. Every other
          label here already says "classified"; this one used to say "finish". */}
      <StatCard
        label="BEST CLASSIFIED POS"
        value={stats.best_classified_position ? `P${stats.best_classified_position}` : "—"}
        note="Highest classification recorded"
      />
    </div>
  );
}

/**
 * The metrics the design asks for that seven source columns cannot support.
 *
 * Rendered explicitly rather than silently omitted: a reader should be able to
 * see that pole rate was considered and is genuinely absent, not overlooked.
 */
export function UnavailableMetrics() {
  return (
    <>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <Badge tone="warning">Missing data</Badge>
        <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
          These metrics are not computed because the required columns are absent from the source. They are
          never estimated.
        </span>
      </div>
      <div className="grid grid--kpi">
        <Unavailable label="POLE RATE" why="No qualifying or grid column in results.csv." />
        <Unavailable label="FASTEST LAPS" why="No fastest-lap column in results.csv." />
        <Unavailable label="DNF RATE" why="No finishing-status column; retirements are ranked, not flagged." />
        <Unavailable label="POINTS / RACE" why="No points column in results.csv." />
      </div>
    </>
  );
}
