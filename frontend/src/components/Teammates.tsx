import { Link } from "react-router-dom";
import { DataTable } from "./DataTable";
import { Async, EmptyState } from "./States";
import { dec, num, pct } from "./format";
import { Badge, SectionTitle, StatCard } from "./ui";
import { MethodologyNote } from "./MethodologyNote";
import { useApi } from "../hooks/useApi";
import type { TeammateResponse, TeammateSpell } from "../types";

/**
 * Teammate head-to-head.
 *
 * The most analytically valuable view in the application: two drivers in the
 * same car in the same race is the only control for machinery this dataset
 * offers. Presented with its limitation attached rather than as a verdict.
 */
export function TeammateSection({ driverId, driverName }: { driverId: number | string; driverName: string }) {
  const state = useApi<TeammateResponse>(`/drivers/${driverId}/teammates`);

  return (
    <>
      <SectionTitle aside="MACHINERY HELD ROUGHLY CONSTANT">Teammate record</SectionTitle>
      <Async state={state} loadingRows={4}>
        {(data) => {
          if (data.spells.length === 0) {
            return (
              <EmptyState
                title="No teammate record"
                body={`${driverName} has no races in the dataset sharing a constructor with another driver.`}
              />
            );
          }

          const { summary } = data;
          const delta = summary.avg_position_delta;

          return (
            <>
              <MethodologyNote metric={data.methodology} />

              {summary.shared_races > 0 ? (
                <div className="grid grid--kpi" style={{ marginBottom: 16 }}>
                  <StatCard
                    label="HEAD-TO-HEAD"
                    value={`${summary.ahead}–${summary.behind}`}
                    note={`Across ${num(summary.shared_races)} shared races`}
                  />
                  <StatCard
                    label="CLASSIFIED AHEAD"
                    value={pct(summary.h2h_rate)}
                    note="Share of shared races"
                  />
                  <StatCard
                    label="AVG POSITION DELTA"
                    value={delta === null ? "—" : `${delta > 0 ? "+" : ""}${dec(delta)}`}
                    note={delta === null ? undefined : delta > 0 ? "Ahead on average" : "Behind on average"}
                  />
                  <StatCard label="TEAMMATES COUNTED" value={num(summary.teammates)} note="Spells above the sample threshold" />
                </div>
              ) : (
                <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
                  <Badge tone="warning">Sample too small</Badge> Every teammate spell for {driverName} is below
                  the minimum shared-race threshold, so no career total is computed. The individual spells are
                  listed below.
                </p>
              )}

              {summary.excluded_short_spells > 0 && summary.shared_races > 0 && (
                <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 0 }}>
                  {summary.excluded_short_spells} short spell
                  {summary.excluded_short_spells === 1 ? "" : "s"} excluded from the totals above and shown
                  below, flagged.
                </p>
              )}

              <DataTable
                caption={`${driverName} head-to-head record against each teammate`}
                rows={data.spells}
                rowKey={(row: TeammateSpell) => `${row.teammate_id}-${row.constructor_id}`}
                columns={[
                  {
                    key: "mate",
                    header: "Teammate",
                    render: (r) => (
                      <Link to={`/drivers/${r.teammate_slug}`}>{r.teammate_name}</Link>
                    ),
                  },
                  {
                    key: "team",
                    header: "Constructor",
                    render: (r) => <Link to={`/constructors/${r.constructor_slug}`}>{r.constructor_name}</Link>,
                  },
                  {
                    key: "seasons",
                    header: "Seasons",
                    render: (r) => (
                      <span className="mono" style={{ fontSize: 12 }}>
                        {r.seasons.length === 1 ? r.seasons[0] : `${r.seasons[0]}–${r.seasons[r.seasons.length - 1]}`}
                      </span>
                    ),
                  },
                  { key: "shared", header: "Shared", numeric: true, render: (r) => num(r.shared_races) },
                  {
                    key: "h2h",
                    header: "H2H",
                    numeric: true,
                    render: (r) => (
                      <span className="mono" style={{ fontWeight: r.ahead > r.behind ? 600 : 400 }}>
                        {r.ahead}–{r.behind}
                      </span>
                    ),
                  },
                  {
                    key: "rate",
                    header: "Ahead %",
                    numeric: true,
                    render: (r) => (
                      <span style={r.comparable ? undefined : { color: "var(--warning)" }}>
                        {pct(r.h2h_rate)}
                        {!r.comparable && <span aria-label=" (small sample)"> *</span>}
                      </span>
                    ),
                  },
                  {
                    key: "delta",
                    header: "Pos delta",
                    numeric: true,
                    render: (r) => (
                      <span className="mono">
                        {r.avg_position_delta > 0 ? "+" : ""}
                        {dec(r.avg_position_delta)}
                      </span>
                    ),
                  },
                  {
                    key: "avgs",
                    header: "Avg (them)",
                    numeric: true,
                    render: (r) => (
                      <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>
                        {dec(r.my_avg_position)} ({dec(r.teammate_avg_position)})
                      </span>
                    ),
                  },
                ]}
              />
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                * fewer than the minimum shared races — shown, but not comparable. “Pos delta” is positive when{" "}
                {driverName} was classified ahead on average.
              </p>
            </>
          );
        }}
      </Async>
    </>
  );
}
