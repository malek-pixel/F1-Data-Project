import { Link } from "react-router-dom";
import { Async } from "../components/States";
import { formatDate, num } from "../components/format";
import { Badge } from "../components/ui";
import { seriesColour as colourFor } from "../charts/palette";
import { useApi } from "../hooks/useApi";
import type { DatasetSummary, Health, Insight, RaceDetail, SeasonRounds, SeasonSummary } from "../types";

/**
 * Overview workstation, built to the mockup's Home section
 * (`design/F1 Dashboard.dc.html` § 02): a six-cell KPI strip, two standings
 * panels, a full-width round-by-round strip, then a three-cell footer row.
 *
 * The mockup's cells are populated with championship points, gaps in points,
 * and lap times. Points now exist (race + sprint); lap times still do not, so
 * those cells carries the nearest metric the data does support -- wins, a gap
 * in wins, a classification -- and the panels say "by wins", never
 * "standings". No cell was left out, and no number was invented.
 */

/** One KPI cell. `sub` renders on the value's baseline, as in the mockup. */
function Kpi({ label, value, sub, note }: { label: string; value: string; sub?: string; note?: string }) {
  return (
    <div className="kpi">
      <div className="kpi__label mono">{label}</div>
      <div className="kpi__value-row">
        <div className="kpi__value mono">{value}</div>
        {sub && <div className="kpi__sub mono">{sub}</div>}
      </div>
      {note && <div className="kpi__note">{note}</div>}
    </div>
  );
}


export function Home() {
  const health = useApi<Health>("/health");
  const dataset = useApi<DatasetSummary>("/dataset/summary");
  // "Latest available season" -- resolved from the data, never hardcoded.
  const latest = health.data?.season_to;
  const season = useApi<SeasonSummary>(latest ? `/seasons/${latest}` : null);
  const rounds = useApi<SeasonRounds>(latest ? `/seasons/${latest}/rounds` : null);
  const insights = useApi<{ insights: Insight[] }>("/insights?limit=1");

  // The final round's full classification, for the latest-result panel. Its id
  // comes from the rounds payload, so this is one request, not one per round.
  const finalRound = rounds.data?.rounds[rounds.data.rounds.length - 1];
  const finalRace = useApi<RaceDetail>(finalRound ? `/races/${finalRound.race_id}` : null);

  return (
    <>
      {/* The design opens Home directly on the KPI strip, with no page title.
          A document still needs one h1, so it is present for assistive tech
          and hidden visually rather than changing the layout. */}
      <h1 className="sr-only">Overview</h1>

      <div className="panel">
        <Async state={season} loadingRows={3}>
          {(summary) => {
            // Championship leaders, from points -- not the wins proxy these
            // KPIs used before points existed.
            const leadDriver = summary.standings.drivers[0];
            const secondDriver = summary.standings.drivers[1];
            const leadTeam = summary.standings.constructors[0];
            const uniqueWinners = summary.drivers.filter((d) => d.wins > 0).length;
            const last = rounds.data?.rounds[rounds.data.rounds.length - 1];
            return (
              <div className="kpi-strip">
                {/* The mockup reads "24 / 24" as rounds completed of rounds
                    scheduled. There is no schedule in the source, so the same
                    shape carries what is knowable: rounds with a recorded
                    winner, over rounds present. */}
                <Kpi
                  label="ROUNDS · CLASSIFIED"
                  value={num(rounds.data?.rounds.filter((r) => r.winner_driver).length ?? summary.races)}
                  sub={`/ ${summary.races}`}
                  note="Rounds with a recorded winner"
                />
                <Kpi
                  label="CHAMPION · DRIVER"
                  value={leadDriver ? leadDriver.name.split(" ").slice(-1)[0] : "—"}
                  sub={leadDriver ? `${num(leadDriver.points)} pts` : undefined}
                  note="Championship leader on points"
                />
                <Kpi
                  label="GAP TO P2"
                  value={
                    leadDriver && secondDriver
                      ? num((leadDriver.points ?? 0) - (secondDriver.points ?? 0))
                      : "—"
                  }
                  sub="points"
                  note="Race and sprint points"
                />
                <Kpi
                  label="CHAMPION · CONSTRUCTOR"
                  value={leadTeam ? leadTeam.name : "—"}
                  sub={leadTeam ? `${num(leadTeam.points)} pts` : undefined}
                  note="Championship leader on points"
                />
                <Kpi label="UNIQUE WINNERS" value={num(uniqueWinners)} note="Drivers with at least one win" />
                <Kpi
                  label="FINAL ROUND · WINNER"
                  value={last?.winner_driver ? last.winner_driver.split(" ").slice(-1)[0] : "—"}
                  note={last ? `${last.circuit_name} · ${formatDate(last.date)}` : undefined}
                />
              </div>
            );
          }}
        </Async>
      </div>

      {/*
        These ARE the championship standings.

        Until points were ingested this page carried a "Not championship
        standings" warning and ranked by wins, which was correct then and
        became false the moment `results.points` existed. Championship totals
        now reproduce the official figures exactly for every season in the
        dataset, sprint points included.

        The only caveat left is the tie-break: ordering on equal points uses
        wins then podiums, where the official rule is a countback. That is
        stated rather than glossed.
      */}
      <p className="note-line">
        <Badge tone="info">Championship points</Badge> Race and sprint points, as awarded. Ties are
        broken by wins, then podiums — the official countback rule is not applied.
      </p>

      <Async state={season} loadingRows={8}>
        {(summary) => {
          const drivers = summary.standings.drivers.slice(0, 8);
          const teams = summary.standings.constructors.slice(0, 8);
          const teamOrder = summary.standings.constructors.map((c) => c.name);
          const leadPoints = teams[0]?.points ?? 0;
          return (
            <div className="split">
              {/* Mockup § 02: standings are grid rows with a team colour bar,
                  not a table. PTS/GAP are now real points, which is what the
                  mockup asked for and what the data finally supports. */}
              <div className="split__pane">
                <div className="pane__head">
                  <h2 className="pane__title">Drivers' Championship</h2>
                  <span className="pane__meta mono">{summary.season} · POINTS</span>
                </div>
                <div className="standings" role="table" aria-label={`${summary.season} drivers' championship standings`}>
                  <div className="standings__head mono" role="row">
                    <span role="columnheader">#</span>
                    <span />
                    <span role="columnheader">DRIVER</span>
                    <span role="columnheader">W</span>
                    <span role="columnheader">PTS</span>
                    <span role="columnheader">GAP</span>
                  </div>
                  {drivers.map((row) => (
                    <Link key={row.id} to={`/drivers/${row.slug}`} className="standings__row" role="row">
                      <span className="mono standings__rank">{row.position}</span>
                      {/* The mockup colours this bar by the driver's team. The
                          standings payload carries no per-driver constructor,
                          so it stays neutral rather than colouring by guess. */}
                      <span className="standings__flag" />
                      <span className="standings__name">
                        {row.name}
                        <span className="mono standings__sub">
                          {num(row.entries)} starts · {num(row.podiums)} podiums
                        </span>
                      </span>
                      <span className="mono standings__num">{num(row.wins)}</span>
                      <span className="mono standings__num standings__num--lead">{num(row.points)}</span>
                      <span className="mono standings__gap">
                        {row.position === 1
                          ? "—"
                          : `−${num((drivers[0].points ?? 0) - (row.points ?? 0))}`}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>

              <div className="split__pane">
                <div className="pane__head">
                  <h2 className="pane__title">Constructors' Championship</h2>
                  <span className="pane__meta mono">{summary.season} · POINTS</span>
                </div>
                <div className="standings standings--team" role="table" aria-label={`${summary.season} constructors' championship standings`}>
                  <div className="standings__head mono" role="row">
                    <span role="columnheader">#</span>
                    <span />
                    <span role="columnheader">CONSTRUCTOR</span>
                    <span role="columnheader">SHARE</span>
                    <span role="columnheader">PTS</span>
                    <span role="columnheader">GAP</span>
                  </div>
                  {teams.map((row) => (
                    <Link key={row.id} to={`/constructors/${row.slug}`} className="standings__row" role="row">
                      <span className="mono standings__rank">{row.position}</span>
                      <span className="standings__flag" style={{ background: colourFor(row.name, teamOrder) }} />
                      <span className="standings__name">{row.name}</span>
                      <span className="standings__share" title={`${row.points} of ${leadPoints} leader points`}>
                        <span
                          style={{
                            width: leadPoints ? `${((row.points ?? 0) / leadPoints) * 100}%` : 0,
                            background: colourFor(row.name, teamOrder),
                          }}
                        />
                      </span>
                      <span className="mono standings__num standings__num--lead">{num(row.points)}</span>
                      <span className="mono standings__gap">
                        {row.position === 1
                          ? "—"
                          : `−${num((teams[0].points ?? 0) - (row.points ?? 0))}`}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          );
        }}
      </Async>

      <div className="panel panel--pad">
        <Async state={rounds} loadingRows={2}>
          {(payload) => {
            const tally = new Map<string, number>();
            for (const round of payload.rounds) {
              if (round.winner_constructor) {
                tally.set(round.winner_constructor, (tally.get(round.winner_constructor) ?? 0) + 1);
              }
            }
            const order = [...tally.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
            return (
              <>
                <div className="pane__head pane__head--flush">
                  <h2 className="pane__title">
                    {payload.season} season · round-by-round winners
                  </h2>
                  <span className="legend mono">
                    {order.map((name) => (
                      <span key={name} className="legend__item">
                        <span className="legend__swatch" style={{ background: colourFor(name, order) }} />
                        {name} {tally.get(name)}
                      </span>
                    ))}
                  </span>
                </div>
                <ol className="strip" aria-label={`${payload.season} winners by round`}>
                  {payload.rounds.map((round) => (
                    <li key={round.race_id} className="strip__cell">
                      <Link
                        to={`/races/${round.race_id}`}
                        title={`R${round.round} · ${round.race_name} · ${round.winner_driver ?? "no winner recorded"}`}
                      >
                        <span
                          className="strip__bar"
                          style={{ background: colourFor(round.winner_constructor, order) }}
                        />
                        <span className="strip__round mono">{String(round.round).padStart(2, "0")}</span>
                      </Link>
                    </li>
                  ))}
                </ol>
                <div className="strip__ends mono">
                  <span>
                    R{String(payload.rounds[0]?.round ?? 1).padStart(2, "0")} ·{" "}
                    {payload.rounds[0]?.circuit_name}
                  </span>
                  <span>
                    R{String(payload.rounds[payload.rounds.length - 1]?.round ?? 1).padStart(2, "0")} ·{" "}
                    {payload.rounds[payload.rounds.length - 1]?.circuit_name}
                  </span>
                </div>
              </>
            );
          }}
        </Async>
      </div>

      <div className="triptych">
        <div className="triptych__cell">
          <div className="kpi__label mono">
            LATEST RESULT{finalRound ? ` · R${finalRound.round} · ${finalRound.circuit_name.toUpperCase()}` : ""}
          </div>
          <Async state={finalRace} loadingRows={3}>
            {(race) => (
              <ol className="podium">
                {race.results.slice(0, 3).map((entry) => (
                  <li key={entry.driver_id}>
                    <span className="podium__pos mono">P{entry.position}</span>
                    <Link to={`/drivers/${entry.driver_slug}`} className="podium__driver">
                      {entry.driver_name}
                    </Link>
                    <span className="podium__team">{entry.constructor_name}</span>
                  </li>
                ))}
              </ol>
            )}
          </Async>
          {/* The mockup shows race time and gaps here. Neither exists in the
              source, so the panel carries the classification instead. */}
          <div className="kpi__note">Classification only — the source carries no race or gap times.</div>
        </div>

        <div className="triptych__cell">
          <div className="kpi__label mono">KEY INSIGHT · CALCULATED</div>
          <Async state={insights} loadingRows={2}>
            {(payload) =>
              payload.insights[0] ? (
                <>
                  <p className="triptych__lead">{payload.insights[0].headline}</p>
                  <p className="kpi__note">{payload.insights[0].detail}</p>
                  <Link to="/records" className="triptych__more">
                    Records &amp; eras →
                  </Link>
                </>
              ) : null
            }
          </Async>
        </div>

        <div className="triptych__cell">
          <div className="kpi__label mono">DATA STATUS</div>
          <Async state={dataset} loadingRows={3}>
            {(summary) => (
              <>
                <dl className="status-list mono">
                  {summary.tables
                    .filter((table) => table.name !== "build_meta")
                    .map((table) => (
                      <div key={table.name}>
                        <dt>{table.name}</dt>
                        <dd>{num(table.rows)} rows</dd>
                      </div>
                    ))}
                </dl>
                <Link to="/dataset" className="triptych__more">
                  Dataset explorer →
                </Link>
              </>
            )}
          </Async>
        </div>
      </div>

      <div className="panel panel--pad">
        <h2 className="pane__title" style={{ marginBottom: 8 }}>
          What this dataset cannot tell you
        </h2>
        <Async state={dataset} loadingRows={2}>
          {(summary) => (
            <>
              <p className="kpi__note" style={{ marginTop: 0 }}>
                These fields are absent from the source. Nothing in this tool estimates them.
              </p>
              <div className="badge-wrap">
                {summary.unavailable_fields.map((field) => (
                  <Badge key={field} tone="warning">
                    {field}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </Async>
      </div>
    </>
  );
}
