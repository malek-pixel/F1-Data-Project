import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { motion } from "motion/react";
import { Stagger, staggerItem } from "../components/motion";
import { SearchField } from "../components/SearchField";
import { Async, EmptyState } from "../components/States";
import { dec, num } from "../components/format";
import { Badge, Cell, CellGrid, PageHeader, Panel, PendingCell, SectionTitle } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage, useDataset } from "../hooks/useDataset";
import { qs } from "../services/api";
import { MethodologyNote } from "../components/MethodologyNote";
import type { Circuit, CircuitDetail as Detail, MetricDoc } from "../types";

const MotionCard = motion.create(Link);

interface Specialist {
  driver_id: number;
  driver_slug: string;
  driver_name: string;
  appearances: number;
  wins: number;
  podiums: number;
  avg_here: number;
  avg_career: number;
  delta_vs_career: number;
}

/**
 * Drivers who over-performed their own career norm here.
 *
 * Ranked by the delta rather than raw results, so a midfield driver who
 * reliably over-delivered is not buried under front-runners who were quick
 * everywhere. Complements "Most successful here", which ranks by wins.
 */
function SpecialistsSection({ circuitId, circuitName }: { circuitId: number; circuitName: string }) {
  const state = useApi<{ specialists: Specialist[]; min_appearances: number; methodology: MetricDoc }>(
    `/circuits/${circuitId}/specialists`,
  );
  return (
    <>
      <SectionTitle aside="RELATIVE TO EACH DRIVER'S CAREER AVERAGE">Over-performers here</SectionTitle>
      <Async state={state} loadingRows={4}>
        {(data) => (
          <>
            <MethodologyNote metric={data.methodology} />
            <DataTable
              caption={`Drivers who outperformed their career average at ${circuitName}`}
              rows={data.specialists.slice(0, 12)}
              rowKey={(row) => row.driver_id}
              emptyMessage={`No driver has at least ${data.min_appearances} appearances here.`}
              columns={[
                { key: "d", header: "Driver", render: (r) => <Link to={`/drivers/${r.driver_slug}`}>{r.driver_name}</Link> },
                { key: "a", header: "Starts", numeric: true, render: (r) => num(r.appearances) },
                { key: "w", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                { key: "h", header: "Avg here", numeric: true, render: (r) => dec(r.avg_here) },
                { key: "c", header: "Avg career", numeric: true, render: (r) => dec(r.avg_career) },
                {
                  key: "delta",
                  header: "vs career",
                  numeric: true,
                  render: (r) => (
                    <span className="mono" style={{ color: r.delta_vs_career > 0 ? "var(--success)" : "var(--text-dim)" }}>
                      {r.delta_vs_career > 0 ? "+" : ""}{dec(r.delta_vs_career)}
                    </span>
                  ),
                },
              ]}
            />
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              Positive means the driver was classified better here than across their career. Minimum{" "}
              {data.min_appearances} appearances.
            </p>
          </>
        )}
      </Async>
    </>
  );
}

/**
 * Track map from the design assets.
 *
 * Circuits without an SVG render an explicit unavailable panel
 * rather than a generic placeholder shape, which would imply we have a map
 * for a track we do not.
 */
function TrackMap({ circuit }: { circuit: Pick<Circuit, "slug" | "name" | "has_map"> }) {
  if (!circuit.has_map) {
    return (
      <div className="circuit-map" style={{ flexDirection: "column", gap: 8 }}>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-faint)", letterSpacing: "0.08em" }}>
          NO TRACK MAP
        </div>
        <p style={{ fontSize: 13, color: "var(--text-faint)", margin: 0, textAlign: "center", maxWidth: "36ch" }}>
          No track outline ships for {circuit.name}. Results below are unaffected.
        </p>
      </div>
    );
  }
  return (
    <div className="circuit-map">
      <img src={`/circuits/${circuit.slug}.svg`} alt={`Track layout of ${circuit.name}`} loading="lazy" decoding="async" width={500} height={500} />
    </div>
  );
}

/**
 * Ranked list with a proportional bar (mockup § 05).
 *
 * The bar is scaled to the leader, so it reads as "share of the best result
 * here" rather than an absolute quantity.
 */
function RankList<T extends { id: number; name: string; wins: number }>({
  rows,
  href,
  note,
}: {
  rows: T[];
  href: (row: T) => string;
  note: (row: T) => string;
}) {
  if (rows.length === 0) return <p className="table-empty">No results recorded here.</p>;
  const top = Math.max(...rows.map((row) => row.wins), 1);
  return (
    <ol className="rank-list">
      {rows.map((row, i) => (
        <li key={row.id}>
          <span className="rank-list__n mono">{i + 1}</span>
          <span style={{ minWidth: 0 }}>
            <Link to={href(row)}>{row.name}</Link>
            <span className="mono rank-list__note">{note(row)}</span>
          </span>
          <span className="rank-list__val mono">{num(row.wins)} wins</span>
          <span className="rank-list__bar" aria-hidden="true">
            <span style={{ width: `${(row.wins / top) * 100}%` }} />
          </span>
        </li>
      ))}
    </ol>
  );
}

export function CircuitLibrary() {
  const info = useDataset();
  const coverage = useCoverage();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search);
  const state = useApi<Circuit[]>(`/circuits${qs({ search: debounced })}`);

  return (
    <>
      <PageHeader
        eyebrow="CIRCUIT LIBRARY"
        title="Circuits"
        sub={`${info ? info.circuits : "—"} circuits hosted a race between ${coverage}. Circuit identity is derived from race name via a curated season-aware map.`}
      />

      <div className="controls">
        <SearchField
          id="circuit-search"
          label="SEARCH"
          className="searchfield--wide"
          placeholder="Circuit or country…"
          value={search}
          loading={state.loading}
          onChange={setSearch}
        />
      </div>

      <Async
        state={state}
        loadingRows={8}
        loadingVariant="cards"
        empty={{ title: "No circuits found", body: `Nothing matches “${debounced}”. Try a country name.` }}
      >
        {(circuits) => (
          /* Track maps are the point of this library, so the card grid is the
             only view -- a row of text could not show a layout. Everything the
             explorer table listed (country, races, top winner) is on the card. */
          <Stagger className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {circuits.map((circuit) => (
              <MotionCard
                key={circuit.id}
                variants={staggerItem}
                to={`/circuits/${circuit.id}`}
                className="card"
                style={{ padding: 16 }}
              >
                <TrackMap circuit={circuit} />
                <div style={{ marginTop: 12, fontWeight: 600, fontSize: 15 }}>{circuit.name}</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                  <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
                    {circuit.country.toUpperCase()} · {circuit.races} races
                  </span>
                  {!circuit.has_map && <Badge tone="warning">No map</Badge>}
                </div>
                <div className="mono" style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 6 }}>
                  {circuit.top_winner ? (
                    <>
                      MOST WINS · {circuit.top_winner} ({circuit.top_winner_wins})
                    </>
                  ) : (
                    "MOST WINS · no recorded winner"
                  )}
                </div>
              </MotionCard>
            ))}
          </Stagger>
        )}
      </Async>
    </>
  );
}

export function CircuitDetail() {
  const { id } = useParams();
  const state = useApi<Detail>(`/circuits/${id}`);

  return (
    <Async state={state} loadingRows={6}>
      {(circuit) => (
        <>
          {/* Mockup section 05: masthead, track map, measured strip. The
              design's LENGTH, LAPS, CORNERS and FIRST GP cells hold their
              place and state that the source cannot fill them. */}
          <Panel>
            <div className="entity-head">
              <div>
                <div className="entity-head__eyebrow mono">CIRCUIT · {circuit.country.toUpperCase()}</div>
                <h1 className="entity-head__name">{circuit.name}</h1>
                <div className="entity-head__sub">
                  {circuit.races} races in dataset · identity derived from race name
                </div>
              </div>
            </div>

            <div className="grid grid--split" style={{ padding: "16px 20px", margin: 0 }}>
              <TrackMap circuit={circuit} />
              <p style={{ fontSize: 13, color: "var(--text-dim)", margin: 0 }}>
                Stats aggregate every classification recorded at this circuit across all seasons it hosted a race.
              </p>
            </div>

            <CellGrid cols={5}>
              <Cell label="RACES" value={num(circuit.races)} />
              <Cell label="ENTRIES" value={num(circuit.stats.entries)} note="Classifications here" />
              <Cell
                label="AVG CLASSIFIED POS"
                value={dec(circuit.stats.avg_classified_position)}
                note="Across all entries here"
              />
              <Cell
                label="WINNERS"
                value={num(new Set(circuit.winners.map((w) => w.driver_id)).size)}
                note="Distinct race winners"
              />
              <Cell
                label="FIRST IN DATASET"
                value={circuit.winners.length ? String(Math.min(...circuit.winners.map((w) => w.season))) : "—"}
                note="Coverage starts in 2000"
              />
            </CellGrid>
            <CellGrid cols={4}>
              <PendingCell label="LENGTH" why="No circuit-length column in the source" />
              <PendingCell label="LAPS" why="No lap-count column in the source" />
              <PendingCell label="CORNERS" why="No layout data in the source" />
              <PendingCell label="FIRST GP" why="Coverage begins in 2000; earlier races are outside the dataset" />
            </CellGrid>
          </Panel>

          {/* Mockup § 05 ranks these as a list with a proportional bar, not a
              table: the comparison being made is one number against the
              leader, and a bar reads faster than a column of digits. */}
          <SectionTitle>Most successful here</SectionTitle>
          <div className="grid grid--2">
            <div className="card">
              <div className="card__label mono">TOP DRIVERS</div>
              <RankList
                rows={circuit.top_drivers}
                href={(row) => `/drivers/${row.id}`}
                note={(row) => `${num(row.podiums)} pod · avg P${dec(row.avg_classified_position)}`}
              />
            </div>
            <div className="card">
              <div className="card__label mono">TOP CONSTRUCTORS</div>
              <RankList
                rows={circuit.top_constructors}
                href={(row) => `/constructors/${row.id}`}
                note={(row) => `${num(row.podiums)} pod · ${num(row.entries)} entries`}
              />
            </div>
          </div>

          <SpecialistsSection circuitId={circuit.id} circuitName={circuit.name} />

          <SectionTitle aside={`${circuit.winners.length} races`}>Winners over time</SectionTitle>
          {circuit.winners.length === 0 ? (
            <EmptyState title="No races recorded" body="This circuit has no race results in the dataset window." />
          ) : (
            <DataTable
              caption={`Every winner at ${circuit.name}`}
              rows={circuit.winners}
              rowKey={(row) => row.race_id}
              columns={[
                {
                  key: "season",
                  header: "Season",
                  render: (r) => <Link to={`/seasons/${r.season}`} className="mono">{r.season}</Link>,
                },
                { key: "race", header: "Race", render: (r) => <Link to={`/races/${r.race_id}`}>{r.race_name}</Link> },
                {
                  key: "driver",
                  header: "Winner",
                  render: (r) => <Link to={`/drivers/${r.driver_slug}`}>{r.driver_name}</Link>,
                },
                {
                  key: "team",
                  header: "Constructor",
                  render: (r) => <Link to={`/constructors/${r.constructor_slug}`}>{r.constructor_name}</Link>,
                },
              ]}
            />
          )}

          <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 24 }}>
            Circuit length, corner count, elevation and lap records are not present in the dataset and are not shown.
          </p>
        </>
      )}
    </Async>
  );
}
