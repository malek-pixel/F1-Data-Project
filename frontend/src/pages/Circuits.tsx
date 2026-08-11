import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { StatBlock } from "../components/StatBlock";
import { Async, EmptyState } from "../components/States";
import { dec, num } from "../components/format";
import { Badge, PageHeader, SectionTitle } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage, useDataset } from "../hooks/useDataset";
import { qs } from "../services/api";
import { MethodologyNote } from "../components/MethodologyNote";
import type { Circuit, CircuitDetail as Detail, MetricDoc } from "../types";

interface Specialist {
  driver_id: number;
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
                { key: "d", header: "Driver", render: (r) => <Link to={`/drivers/${r.driver_id}`}>{r.driver_name}</Link> },
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
      <img src={`/circuits/${circuit.slug}.svg`} alt={`Track layout of ${circuit.name}`} loading="lazy" />
    </div>
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
        <div className="field">
          <label htmlFor="circuit-search">SEARCH</label>
          <input
            id="circuit-search"
            className="input"
            type="search"
            placeholder="Circuit or country…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            style={{ minWidth: 260 }}
          />
        </div>
      </div>

      <Async
        state={state}
        loadingRows={8}
        empty={{ title: "No circuits found", body: `Nothing matches “${debounced}”. Try a country name.` }}
      >
        {(circuits) => (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
            {circuits.map((circuit) => (
              <Link key={circuit.id} to={`/circuits/${circuit.id}`} className="card" style={{ padding: 16 }}>
                <TrackMap circuit={circuit} />
                <div style={{ marginTop: 12, fontWeight: 600, fontSize: 15 }}>{circuit.name}</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6 }}>
                  <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>
                    {circuit.country.toUpperCase()}
                  </span>
                  {!circuit.has_map && <Badge tone="warning">No map</Badge>}
                </div>
              </Link>
            ))}
          </div>
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
          <PageHeader eyebrow="CIRCUIT" title={circuit.name} sub={circuit.country} />

          <div className="grid grid--split">
            <TrackMap circuit={circuit} />
            <div>
              <StatBlock stats={circuit.stats} entryNoun="entries" />
              <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
                Stats aggregate every classification recorded at this circuit across all seasons it hosted a race.
              </p>
            </div>
          </div>

          <SectionTitle>Most successful here</SectionTitle>
          <div className="grid grid--2">
            <div className="card">
              <div className="card__label mono">TOP DRIVERS</div>
              <DataTable
                caption={`Most successful drivers at ${circuit.name}`}
                rows={circuit.top_drivers}
                rowKey={(row) => row.id}
                columns={[
                  { key: "name", header: "Driver", render: (r) => <Link to={`/drivers/${r.id}`}>{r.name}</Link> },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
                  { key: "avg", header: "Avg pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
                ]}
              />
            </div>
            <div className="card">
              <div className="card__label mono">TOP CONSTRUCTORS</div>
              <DataTable
                caption={`Most successful constructors at ${circuit.name}`}
                rows={circuit.top_constructors}
                rowKey={(row) => row.id}
                columns={[
                  {
                    key: "name",
                    header: "Constructor",
                    render: (r) => <Link to={`/constructors/${r.id}`}>{r.name}</Link>,
                  },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
                ]}
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
                  render: (r) => <Link to={`/drivers/${r.driver_id}`}>{r.driver_name}</Link>,
                },
                {
                  key: "team",
                  header: "Constructor",
                  render: (r) => <Link to={`/constructors/${r.constructor_id}`}>{r.constructor_name}</Link>,
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
