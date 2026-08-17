import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Async } from "../components/States";
import { dec, formatDate, num, pct } from "../components/format";
import {
  Badge,
  Cell,
  CellGrid,
  FilterChip,
  PageHeader,
  PaneHead,
  Panel,
  PendingCell,
  PendingValue,
  Segmented,
} from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { count, useDataset } from "../hooks/useDataset";
import { qs } from "../services/api";
import { seriesColour } from "../charts/palette";
import type {
  Race,
  RaceDetail as RaceDetailType,
  SeasonIndexRow,
  SeasonRounds,
  SeasonSummary,
} from "../types";

interface Dominance {
  races: number;
  distinct_driver_winners: number;
  distinct_constructor_winners: number;
  top_driver_win_share: number | null;
  top_constructor_win_share: number | null;
  drivers: { name: string }[];
  basis: string;
}

/**
 * Repeated wherever a WINS-ordered table appears.
 *
 * This used to say championship order could not be reproduced, because no
 * points column existed. It does now, and the standings on the season page
 * reproduce the official order exactly -- so the note explains what this
 * particular table is ordered by, instead of denying the championship exists.
 */
function RankingBasisNote() {
  return (
    <p className="note-line">
      <Badge tone="info">Ordered by wins</Badge> Ranked by wins, then podiums, then average classified
      position. For the points championship, see the standings on the season page.
    </p>
  );
}

/* ==========================================================================
   Seasons
   ========================================================================== */

/**
 * Season index. The mockup (§ 07) leads with a grid of year chips rather than
 * a table -- 26 seasons is a set you pick from, not a list you scan -- with
 * the table kept underneath for the per-season counts it carries.
 */
export function SeasonIndex() {
  const state = useApi<SeasonIndexRow[]>("/seasons");
  const info = useDataset();
  return (
    <>
      <PageHeader
        eyebrow="SEASON EXPLORER"
        title="Seasons"
        sub={`${count(info?.seasons, "seasons")}, ${count(info?.races, "races")}, ${
          info ? `${info.season_from}–${info.season_to}` : "—"
        }.`}
      />

      <Async state={state} loadingRows={4}>
        {(seasons) => (
          <>
            <Panel pad>
              <PaneHead
                title={`${seasons.length} seasons`}
                meta={`${seasons[seasons.length - 1]?.season} → ${seasons[0]?.season}`}
                flush
              />
              <div className="year-grid">
                {[...seasons].reverse().map((row) => (
                  <Link key={row.season} to={`/seasons/${row.season}`} className="year-chip mono">
                    <span className="year-chip__yr">{row.season}</span>
                    <span className="year-chip__n">{row.races} rounds</span>
                  </Link>
                ))}
              </div>
            </Panel>

            <Panel>
              <PaneHead title="Season totals" meta="ROUNDS · DRIVERS · CONSTRUCTORS · CLASSIFICATIONS" />
              <DataTable
                caption="Seasons in the dataset"
                rows={seasons}
                rowKey={(row) => row.season}
                columns={[
                  {
                    key: "season",
                    header: "Season",
                    render: (r) => (
                      <Link to={`/seasons/${r.season}`} className="mono" style={{ fontWeight: 600 }}>
                        {r.season}
                      </Link>
                    ),
                  },
                  { key: "races", header: "Rounds", numeric: true, render: (r) => num(r.races) },
                  { key: "drivers", header: "Drivers", numeric: true, render: (r) => num(r.drivers) },
                  { key: "constructors", header: "Constructors", numeric: true, render: (r) => num(r.constructors) },
                  { key: "entries", header: "Classifications", numeric: true, render: (r) => num(r.entries) },
                  {
                    key: "wdc",
                    header: "WDC",
                    render: () => <PendingValue title="Champions require a points column; results.csv has none" />,
                  },
                ]}
              />
            </Panel>
          </>
        )}
      </Async>
    </>
  );
}

export function SeasonDetail() {
  const { season } = useParams();
  const [tab, setTab] = useState<"drivers" | "constructors">("drivers");
  const state = useApi<SeasonSummary>(`/seasons/${season}`);
  const dominance = useApi<Dominance>(`/seasons/${season}/dominance`);
  const rounds = useApi<SeasonRounds>(`/seasons/${season}/rounds`);

  return (
    <Async state={state} loadingRows={6}>
      {(summary) => {
        const table = tab === "drivers" ? summary.drivers : summary.constructors;
        const totalWins = table.reduce((sum, row) => sum + row.wins, 0);
        return (
          <>
            {/* Mockup section 07: masthead, then a six-cell measured strip.
                WDC and WCC keep their cells and say why they are empty. */}
            <Panel>
              <div className="entity-head">
                <div>
                  <div className="entity-head__eyebrow mono">SEASON</div>
                  <h1 className="entity-head__name">{summary.season}</h1>
                  <div className="entity-head__sub">
                    {summary.races} rounds · {summary.entries.toLocaleString()} classifications
                  </div>
                </div>
                <div className="entity-head__actions">
                  <Link className="btn" to={`/races${qs({ season: summary.season })}`}>
                    All races
                  </Link>
                </div>
              </div>

              <CellGrid cols={6}>
                <Cell label="ROUNDS" value={num(summary.races)} />
                <Cell
                  label="DRIVERS"
                  value={num(summary.drivers.length)}
                  note="Classified at least once"
                />
                <Cell label="CONSTRUCTORS" value={num(summary.constructors.length)} />
                <Cell
                  label="CLASSIFICATIONS"
                  value={num(summary.entries)}
                  note="One row per driver per race"
                />
                <PendingCell label="WDC WINNER" why="Champions require a points column; the source has none" />
                <PendingCell label="WCC WINNER" why="Champions require a points column; the source has none" />
              </CellGrid>
            </Panel>

            <Async state={dominance} loadingRows={2}>
              {(dom) => (
                <Panel>
                  <PaneHead title="Season concentration" meta="NORMALISED BY RACES HELD" />
                  <CellGrid cols={4}>
                    <Cell
                      label="LEADER WIN SHARE"
                      value={
                        dom.top_driver_win_share === null ? "—" : `${(dom.top_driver_win_share * 100).toFixed(0)}%`
                      }
                      note={dom.drivers[0] ? `${dom.drivers[0].name} — of ${dom.races} races` : undefined}
                    />
                    <Cell
                      label="DIFFERENT RACE WINNERS"
                      value={String(dom.distinct_driver_winners)}
                      note="Drivers who won at least one race"
                    />
                    <Cell
                      label="WINNING CONSTRUCTORS"
                      value={String(dom.distinct_constructor_winners)}
                      note="Teams who won at least one race"
                    />
                    <Cell
                      label="TOP TEAM WIN SHARE"
                      value={
                        dom.top_constructor_win_share === null
                          ? "—"
                          : `${(dom.top_constructor_win_share * 100).toFixed(0)}%`
                      }
                    />
                  </CellGrid>
                  <p className="panel--pad kpi__note" style={{ margin: 0 }}>
                    {dom.basis}
                  </p>
                </Panel>
              )}
            </Async>

            {/* Round-by-round winner strip, as on the overview. */}
            <Panel pad>
              <Async state={rounds} loadingRows={2}>
                {(payload) => {
                  const tally = new Map<string, number>();
                  for (const round of payload.rounds) {
                    if (round.winner_constructor) {
                      tally.set(round.winner_constructor, (tally.get(round.winner_constructor) ?? 0) + 1);
                    }
                  }
                  const order = [...tally.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
                  const colour = (name: string | null) => seriesColour(name, order);
                  return (
                    <>
                      <PaneHead
                        flush
                        title={`${payload.season} · round-by-round winners`}
                        meta={
                          <span className="legend">
                            {order.map((name) => (
                              <span key={name} className="legend__item">
                                <span className="legend__swatch" style={{ background: colour(name) }} />
                                {name} {tally.get(name)}
                              </span>
                            ))}
                          </span>
                        }
                      />
                      <ol className="strip" aria-label={`${payload.season} winners by round`}>
                        {payload.rounds.map((round) => (
                          <li key={round.race_id} className="strip__cell">
                            <Link
                              to={`/races/${round.race_id}`}
                              title={`R${round.round} · ${round.race_name} · ${
                                round.winner_driver ?? "no winner recorded"
                              }`}
                            >
                              <span className="strip__bar" style={{ background: colour(round.winner_constructor) }} />
                              <span className="strip__round mono">{String(round.round).padStart(2, "0")}</span>
                            </Link>
                          </li>
                        ))}
                      </ol>
                    </>
                  );
                }}
              </Async>
            </Panel>

            <RankingBasisNote />

            <Panel>
              <PaneHead
                title={`${summary.season} ${tab} · by wins`}
                meta={
                  <Segmented
                    label="Ranking type"
                    active={tab}
                    onChange={setTab}
                    options={[
                      { id: "drivers", label: "Drivers" },
                      { id: "constructors", label: "Constructors" },
                    ]}
                  />
                }
              />
              <DataTable
                caption={`${summary.season} ${tab} ranked by wins`}
                rows={table}
                rowKey={(row) => row.id}
                columns={[
                  {
                    key: "pos",
                    header: "Pos",
                    numeric: true,
                    render: (_r, i) => <span className="mono rank">{i + 1}</span>,
                  },
                  {
                    key: "name",
                    header: tab === "drivers" ? "Driver" : "Constructor",
                    render: (r) => <Link to={`/${tab}/${r.id}`}>{r.name}</Link>,
                  },
                  { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
                  { key: "wins", header: "W", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  {
                    key: "share",
                    header: "Win share",
                    numeric: true,
                    render: (r) => (totalWins ? pct(r.wins / totalWins, 0) : "—"),
                  },
                  { key: "avg", header: "Avg P", numeric: true, render: (r) => dec(r.avg_classified_position) },
                  {
                    key: "pts",
                    header: "Pts",
                    numeric: true,
                    render: () => <PendingValue title="No points column in results.csv" />,
                  },
                ]}
              />
            </Panel>

            <Panel>
              <PaneHead title="Calendar" meta={`${summary.races} ROUNDS`} />
              <DataTable
                caption={`${summary.season} race calendar`}
                rows={summary.races_list}
                rowKey={(row) => row.id}
                columns={[
                  { key: "round", header: "Rd", numeric: true, render: (r) => <span className="mono">{r.round}</span> },
                  { key: "name", header: "Race", render: (r) => <Link to={`/races/${r.id}`}>{r.name}</Link> },
                  {
                    key: "circuit",
                    header: "Circuit",
                    render: (r) => <Link to={`/circuits/${r.circuit_id}`}>{r.circuit_name}</Link>,
                  },
                  { key: "date", header: "Date", render: (r) => <span className="mono">{formatDate(r.date)}</span> },
                  {
                    key: "winner",
                    header: "Winner",
                    render: (r) =>
                      r.winner_driver ? (
                        <Link to={`/drivers/${r.winner_driver_slug}`}>{r.winner_driver}</Link>
                      ) : (
                        <PendingValue title="No recorded winner for this race" />
                      ),
                  },
                ]}
              />
            </Panel>
          </>
        );
      }}
    </Async>
  );
}

/* ==========================================================================
   Races
   ========================================================================== */

export function RaceIndex() {
  // Defaults to the latest season present in the data. A hardcoded year
  // silently points at a season that may not exist after a data refresh.
  const info = useDataset();
  const [season, setSeason] = useState<number | "" | null>(null);
  const [circuitId, setCircuitId] = useState<number | "">("");
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search);

  const seasons = useApi<SeasonIndexRow[]>("/seasons");
  const circuits = useApi<{ id: number; name: string }[]>("/circuits");
  const active = season === null ? (info?.season_to ?? "") : season;
  const races = useApi<Race[]>(
    `/races${qs({ season: active || undefined, circuit_id: circuitId || undefined, limit: 500 })}`,
  );

  // Race-name / winner search is applied client-side over one season's rows.
  // The API has no race-name search, and adding one to filter at most 24 rows
  // already in memory would be a query for nothing.
  const filter = (rows: Race[]) =>
    debounced
      ? rows.filter((row) =>
          `${row.name} ${row.circuit_name} ${row.winner_driver ?? ""}`
            .toLowerCase()
            .includes(debounced.toLowerCase()),
        )
      : rows;

  const clearAll = () => {
    setSeason("");
    setCircuitId("");
    setSearch("");
  };

  return (
    <>
      <PageHeader
        eyebrow="RACE EXPLORER"
        title="Races"
        sub="Every Grand Prix in the dataset has a row and a detail page. Filter by season or circuit."
      />

      <div className="controls">
        <div className="field">
          <label htmlFor="race-search">SEARCH</label>
          <input
            id="race-search"
            className="input"
            type="search"
            placeholder="Race, circuit or winner…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ minWidth: 220 }}
          />
        </div>
        <div className="field">
          <label htmlFor="race-season">SEASON</label>
          <select
            id="race-season"
            className="select"
            value={active}
            onChange={(event) => setSeason(event.target.value ? Number(event.target.value) : "")}
          >
            <option value="">All seasons</option>
            {(seasons.data ?? []).map((row) => (
              <option key={row.season} value={row.season}>
                {row.season}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="race-circuit">CIRCUIT</label>
          <select
            id="race-circuit"
            className="select"
            value={circuitId}
            onChange={(event) => setCircuitId(event.target.value ? Number(event.target.value) : "")}
          >
            <option value="">All circuits</option>
            {(circuits.data ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <Async
        state={races}
        loadingRows={8}
        empty={{ title: "No races", body: "No races recorded for this selection." }}
      >
        {(rows) => {
          const visible = filter(rows);
          return (
            <Panel>
              <PaneHead
                title={`Races · ${visible.length} rows`}
                meta={active ? `SEASON ${active}` : "ALL SEASONS"}
              />
              {(debounced || circuitId || active) && (
                <div className="filter-row">
                  <span className="mono filter-row__label">ACTIVE</span>
                  {active !== "" && <FilterChip label={`season: ${active}`} onClear={() => setSeason("")} />}
                  {circuitId !== "" && (
                    <FilterChip
                      label={`circuit: ${circuits.data?.find((c) => c.id === circuitId)?.name ?? circuitId}`}
                      onClear={() => setCircuitId("")}
                    />
                  )}
                  {debounced && <FilterChip label={`text: ${debounced}`} onClear={() => setSearch("")} />}
                  <button className="chip__clear mono" onClick={clearAll}>
                    Clear all
                  </button>
                </div>
              )}
              <DataTable
                caption="Races"
                rows={visible}
                rowKey={(row) => row.id}
                emptyMessage="No races match these filters."
                columns={[
                  {
                    key: "round",
                    header: "Rd",
                    numeric: true,
                    render: (r) => <span className="mono rank">{String(r.round).padStart(2, "0")}</span>,
                  },
                  {
                    key: "name",
                    header: "Race · circuit",
                    /* Mockup § 06 puts the track outline in the row itself.
                       Circuits without an SVG simply render no thumbnail. */
                    render: (r) => (
                      <span className="race-row">
                        <img
                          className="race-row__map"
                          src={`/circuits/${r.circuit_slug}.svg`}
                          alt=""
                          loading="lazy"
                          onError={(event) => {
                            event.currentTarget.style.visibility = "hidden";
                          }}
                        />
                        <span style={{ minWidth: 0 }}>
                          <Link to={`/races/${r.id}`} style={{ fontWeight: 500 }}>
                            {r.name}
                          </Link>
                          <span className="mono race-row__sub">
                            {r.season} · {r.circuit_name}
                          </span>
                        </span>
                      </span>
                    ),
                  },
                  { key: "date", header: "Date", render: (r) => <span className="mono">{formatDate(r.date)}</span> },
                  {
                    key: "winner",
                    header: "Winner",
                    render: (r) =>
                      r.winner_driver ? (
                        <Link to={`/drivers/${r.winner_driver_slug}`}>{r.winner_driver}</Link>
                      ) : (
                        <PendingValue title="No recorded winner for this race" />
                      ),
                  },
                  {
                    key: "constr",
                    header: "Constr.",
                    render: (r) =>
                      r.winner_constructor ? (
                        <Link to={`/constructors/${r.winner_constructor_slug}`}>{r.winner_constructor}</Link>
                      ) : (
                        <PendingValue />
                      ),
                  },
                  /* The mockup's POLE, GRID, GAP and STATUS columns. None of
                     the four is in the seven source columns. */
                  { key: "pole", header: "Pole", render: () => <PendingValue title="No qualifying data in the source" /> },
                  { key: "grid", header: "Grid", render: () => <PendingValue title="No grid column in the source" /> },
                  { key: "gap", header: "Gap", render: () => <PendingValue title="No race or gap times in the source" /> },
                  {
                    key: "status",
                    header: "Status",
                    render: () => <PendingValue title="No finishing-status column in the source" />,
                  },
                ]}
              />
            </Panel>
          );
        }}
      </Async>
      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
        Columns showing — need source columns the dataset does not carry yet: qualifying, grid, race times and
        finishing status.
      </p>
    </>
  );
}

export function RaceDetail() {
  const { id } = useParams();
  const state = useApi<RaceDetailType>(`/races/${id}`);

  return (
    <Async state={state} loadingRows={6}>
      {(race) => (
        <>
          {/* Mockup section 06 detail: masthead, measured strip, podium, then
              the full classification. */}
          <Panel>
            <div className="entity-head">
              <div>
                <div className="entity-head__eyebrow mono">
                  RD {String(race.round).padStart(2, "0")} · {formatDate(race.date).toUpperCase()}
                </div>
                <h1 className="entity-head__name">
                  {race.season} {race.name}
                </h1>
                <div className="entity-head__sub">
                  <Link to={`/circuits/${race.circuit_id}`}>{race.circuit_name}</Link> ·{" "}
                  <Link to={`/seasons/${race.season}`}>{race.season} season</Link>
                </div>
              </div>
            </div>

            <CellGrid cols={5}>
              <Cell label="CLASSIFIED" value={num(race.results.length)} note="Rows in the source for this race" />
              <Cell
                label="WINNER"
                value={race.results[0]?.driver_name.split(" ").slice(-1)[0] ?? "—"}
                note={race.results[0]?.constructor_name}
              />
              <PendingCell label="DISTANCE" why="No race-distance column in the source" />
              <PendingCell label="LAPS" why="No lap-count column in the source" />
              <PendingCell label="STARTERS" why="No status column: non-starters cannot be told apart" />
            </CellGrid>
          </Panel>

          <div className="split">
            <div className="split__pane">
              <PaneHead title="Podium" meta="CLASSIFIED P1–P3" />
              <div className="panel--pad">
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
                <div className="kpi__note">
                  The mockup shows race time and gaps here. Neither is in the source.
                </div>
              </div>
            </div>
            <div className="split__pane">
              <PaneHead title="Not recorded for this race" meta="WOULD NEED NEW SOURCE COLUMNS" />
              <CellGrid cols={2}>
                <PendingCell label="POLE POSITION" why="No qualifying data in the source" />
                <PendingCell label="FASTEST LAP" why="No fastest-lap column in the source" />
                <PendingCell label="POINTS AWARDED" why="No points column in the source" />
                <PendingCell label="RETIREMENTS" why="No finishing-status column; retirements are ranked, not flagged" />
              </CellGrid>
            </div>
          </div>

          <p className="note-line">
            <Badge tone="warning">Classification order</Badge> Positions are the final classification, which
            includes retirements. The source has no status column, so a retirement cannot be distinguished from a
            finish.
          </p>

          <Panel>
            <PaneHead title="Classification" meta={`${race.results.length} ROWS`} />
            <DataTable
              caption={`${race.season} ${race.name} classification`}
              rows={race.results}
              rowKey={(row) => row.driver_id}
              columns={[
                {
                  key: "pos",
                  header: "Pos",
                  numeric: true,
                  render: (r) => (
                    <span
                      className="mono"
                      style={r.position <= 3 ? { color: "var(--accent-text)", fontWeight: 600 } : undefined}
                    >
                      {r.position}
                    </span>
                  ),
                },
                {
                  key: "driver",
                  header: "Driver",
                  render: (r) => <Link to={`/drivers/${r.driver_slug}`}>{r.driver_name}</Link>,
                },
                {
                  key: "team",
                  header: "Constructor",
                  render: (r) => <Link to={`/constructors/${r.constructor_slug}`}>{r.constructor_name}</Link>,
                },
                { key: "grid", header: "Grid", render: () => <PendingValue title="No grid column in the source" /> },
                {
                  key: "gap",
                  header: "Time / gap",
                  render: () => <PendingValue title="No race or gap times in the source" />,
                },
                {
                  key: "pts",
                  header: "Pts",
                  numeric: true,
                  render: () => <PendingValue title="No points column in the source" />,
                },
                {
                  key: "status",
                  header: "Status",
                  render: () => <PendingValue title="No finishing-status column in the source" />,
                },
              ]}
            />
          </Panel>

          {/* Mockup § 06 closes the race page with a related-links strip. */}
          <div className="related mono">
            <span className="related__label">RELATED</span>
            <Link to={`/seasons/${race.season}`}>{race.season} season →</Link>
            <Link to={`/circuits/${race.circuit_id}`}>{race.circuit_name} →</Link>
            {race.results[0] && (
              <>
                <Link to={`/drivers/${race.results[0].driver_slug}`}>{race.results[0].driver_name} →</Link>
                <Link to={`/constructors/${race.results[0].constructor_slug}`}>
                  {race.results[0].constructor_name} →
                </Link>
              </>
            )}
            <span className="related__note">
              Qualifying, fastest-lap and pit-stop data are outside this dataset.
            </span>
          </div>
        </>
      )}
    </Async>
  );
}
