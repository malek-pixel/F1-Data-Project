import { Link } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Async } from "../components/States";
import { dec, formatDate, num } from "../components/format";
import { Badge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { DatasetSummary, Health, Insight, RaceDetail, SeasonRounds, SeasonSummary } from "../types";

/**
 * Overview workstation, built to the mockup's Home section
 * (`design/F1 Dashboard.dc.html` § 02): a six-cell KPI strip, two standings
 * panels, a full-width round-by-round strip, then a three-cell footer row.
 *
 * The mockup's cells are populated with championship points, gaps in points,
 * and lap times. The source has no points column and no lap times, so each of
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

/**
 * Constructor colours for the round strip.
 *
 * Assigned by rank within the selected season, not from a table of team
 * liveries: the dataset spans 2000-2025, teams change owner and colour, and
 * several no longer exist. A positional palette stays legible without
 * asserting a brand identity the data does not carry.
 */
const STRIP_COLOURS = ["#E10600", "#0090FF", "#F59E0B", "#22C55E", "#A855F7", "#14B8A6", "#EC4899", "#94A3B8"];

function colourFor(name: string | null, order: string[]): string {
  if (!name) return "var(--border)";
  const i = order.indexOf(name);
  return i === -1 ? "var(--text-faint)" : STRIP_COLOURS[i % STRIP_COLOURS.length];
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
      <div className="panel">
        <Async state={season} loadingRows={3}>
          {(summary) => {
            const leadDriver = summary.drivers[0];
            const secondDriver = summary.drivers[1];
            const leadTeam = summary.constructors[0];
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
                  label="LEADER · DRIVER (BY WINS)"
                  value={leadDriver ? leadDriver.name.split(" ").slice(-1)[0] : "—"}
                  sub={leadDriver ? `${leadDriver.wins} wins` : undefined}
                  note="Not a championship position"
                />
                <Kpi
                  label="GAP TO P2 (WINS)"
                  value={leadDriver && secondDriver ? String(leadDriver.wins - secondDriver.wins) : "—"}
                  sub="wins"
                  note="Points gap unavailable — no points column"
                />
                <Kpi
                  label="LEADER · CONSTRUCTOR (BY WINS)"
                  value={leadTeam ? leadTeam.name : "—"}
                  sub={leadTeam ? `${leadTeam.wins} wins` : undefined}
                  note="Not a championship position"
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

      <p className="note-line">
        <Badge tone="warning">Not championship standings</Badge> Ranked by wins, then podiums, then average
        classified position — the dataset carries no points column.
      </p>

      <Async state={season} loadingRows={8}>
        {(summary) => (
          <div className="split">
            <div className="split__pane">
              <div className="pane__head">
                <span className="pane__title">Drivers · by wins</span>
                <span className="pane__meta mono">{summary.season} · WINS · PODIUMS · AVG P</span>
              </div>
              <DataTable
                caption={`${summary.season} drivers ranked by wins`}
                rows={summary.drivers.slice(0, 8)}
                rowKey={(row) => row.id}
                columns={[
                  { key: "rank", header: "#", numeric: true, render: (_r, i) => <span className="mono">{i + 1}</span> },
                  { key: "name", header: "Driver", render: (r) => <Link to={`/drivers/${r.id}`}>{r.name}</Link> },
                  { key: "wins", header: "W", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "avg", header: "Avg P", numeric: true, render: (r) => dec(r.avg_classified_position) },
                ]}
              />
            </div>
            <div className="split__pane">
              <div className="pane__head">
                <span className="pane__title">Constructors · by wins</span>
                <span className="pane__meta mono">{summary.season} · WINS · PODIUMS · AVG P</span>
              </div>
              <DataTable
                caption={`${summary.season} constructors ranked by wins`}
                rows={summary.constructors.slice(0, 8)}
                rowKey={(row) => row.id}
                columns={[
                  { key: "rank", header: "#", numeric: true, render: (_r, i) => <span className="mono">{i + 1}</span> },
                  {
                    key: "name",
                    header: "Constructor",
                    render: (r) => <Link to={`/constructors/${r.id}`}>{r.name}</Link>,
                  },
                  { key: "wins", header: "W", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "avg", header: "Avg P", numeric: true, render: (r) => dec(r.avg_classified_position) },
                ]}
              />
            </div>
          </div>
        )}
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
                  <span className="pane__title">
                    {payload.season} season · round-by-round winners
                  </span>
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
                    <Link to={`/drivers/${entry.driver_id}`} className="podium__driver">
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
                  <Link to="/insights" className="triptych__more">
                    All insights →
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
        <div className="pane__title" style={{ marginBottom: 8 }}>
          What this dataset cannot tell you
        </div>
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
              <p style={{ fontSize: 13, marginBottom: 0, marginTop: 16 }}>
                <Link to="/methodology" style={{ color: "var(--info)" }}>
                  Read the full methodology →
                </Link>
              </p>
            </>
          )}
        </Async>
      </div>
    </>
  );
}
