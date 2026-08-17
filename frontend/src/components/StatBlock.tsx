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
 *     "average finish". Retirements are ranked, not excluded, so the mean
 *     includes them. `DNF RATE` is the direct measure of that and sits
 *     alongside it.
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
      {/* Points, DNFs and grid were shown as "unavailable" long after they
          were ingested. They are real columns; null here now means this
          entity genuinely has none, not that the dataset lacks the field. */}
      <StatCard label="POINTS" value={dec(stats.points)} note="As awarded each season, incl. sprints" />
      <StatCard
        label="DNF RATE"
        value={pct(stats.dnf_rate)}
        note={stats.dnfs === null ? "No status data for these entries" : `${num(stats.dnfs)} of ${num(stats.entries)} entries`}
      />
      <StatCard label="AVG GRID" value={dec(stats.avg_grid)} note="Pit-lane starts excluded, not counted as 0" />
      <StatCard
        label="AVG PLACES GAINED"
        value={dec(stats.avg_positions_gained)}
        note="Grid minus finish, classified finishes only"
      />
    </div>
  );
}

/**
 * The metrics that genuinely have no source, rendered rather than omitted.
 *
 * A reader should be able to see that fastest laps were considered and are
 * absent, not overlooked.
 *
 * This list used to include pole rate, DNF rate and points per race. All
 * three were ingested and the panel went on calling them unavailable, so the
 * UI was telling users a column was missing while the API served it. Only
 * things with no source at all belong here.
 */
export function UnavailableMetrics() {
  return (
    <>
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <Badge tone="warning">Missing data</Badge>
        <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
          These are not computed because no source supplies them. They are never estimated. What the
          dataset does have is reported by the dataset summary, which counts rows rather than relying
          on a list like this one staying current.
        </span>
      </div>
      <div className="grid grid--kpi">
        {/* The AWARD, not the measurement. No source publishes who received
            the fastest-lap point, and since 2019 it has eligibility rules. The
            quickest lap actually driven IS derived from the timings and shown
            on each race page, labelled "quickest lap" to keep the two
            distinct. */}
        <Unavailable label="FASTEST-LAP AWARDS" why="No source records who received the point." />
        <Unavailable label="SECTOR TIMES" why="No source supplies sector splits." />
        <Unavailable label="TYRE COMPOUND" why="No source supplies tyre data." />
        <Unavailable label="CAR / ENGINE SPEC" why="No source supplies chassis or engine detail." />
      </div>
    </>
  );
}
