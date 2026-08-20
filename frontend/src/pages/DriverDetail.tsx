import { Link, useParams } from "react-router-dom";
import { AvgPositionBySeason, WinsBySeason } from "../charts/SeasonCharts";
import { DataTable } from "../components/DataTable";
import { TeammateSection } from "../components/Teammates";
import { CircuitStrengthSection, ConsistencySection } from "../components/Consistency";
import { Async } from "../components/States";
import { driverPhoto } from "../components/driverPhoto";
import { dec, num, pct, seasonSpan } from "../components/format";
import { Cell, CellGrid, PaneHead, Panel, PendingCell, SectionTitle } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import type { ConstructorSpell, DriverDetail as Detail, DriverQualifying, SeasonStats } from "../types";

export function DriverDetail() {
  const { id } = useParams();
  const coverage = useCoverage();
  const detail = useApi<Detail>(`/drivers/${id}`);
  const seasons = useApi<SeasonStats[]>(`/drivers/${id}/seasons`);
  const qualifying = useApi<DriverQualifying>(`/drivers/${id}/qualifying`);

  return (
    <Async state={detail} loadingRows={6}>
      {(driver) => (
        <>
          {/* Mockup § 03: entity masthead, then a measured header strip, then
              the team timeline. Nationality and car number sit in the masthead
              in the design; neither is in the source, so they are stated as
              pending in the strip rather than quietly dropped. */}
          <Panel>
            <div className="entity-head">
              <div>
                <div className="entity-head__eyebrow mono">DRIVER</div>
                <h1 className="entity-head__name">{driver.name}</h1>
                <div className="entity-head__sub">
                  {seasonSpan(driver.constructors.map((spell) => spell.season))} ·{" "}
                  {[...new Set(driver.constructors.map((s) => s.constructor_name))].join(" · ")}
                </div>
              </div>
              <div className="entity-head__actions">
                <Link className="btn" to={`/compare?kind=drivers&left=${driver.slug}`}>
                  Compare
                </Link>
                {/* Mockup § 03 puts a portrait beside the masthead. Every
                    driver has one today; the frame is the fallback for a
                    driver a later ETL run adds before their photo exists. */}
                {driverPhoto(driver.name) ? (
                  <div className="entity-head__portrait gallery__media gallery__media--portrait">
                    <img src={driverPhoto(driver.name)!} alt="" decoding="async" width={340} height={340} />
                  </div>
                ) : (
                  <div className="entity-head__portrait gallery__media mono">
                    PORTRAIT
                    <span>to be added</span>
                  </div>
                )}
              </div>
            </div>

            <CellGrid cols={6}>
              <Cell label="STARTS" value={num(driver.stats.entries)} note="Classifications, incl. retirements" />
              <Cell label="WINS" value={num(driver.stats.wins)} />
              <Cell label="PODIUMS" value={num(driver.stats.podiums)} note="Classified P1–P3" />
              <Cell
                label="WIN RATE"
                value={pct(driver.stats.win_rate)}
                note={`${num(driver.stats.wins)} / ${num(driver.stats.entries)}`}
              />
              <Cell
                label="PODIUM RATE"
                value={pct(driver.stats.podium_rate)}
                note={`${num(driver.stats.podiums)} of ${num(driver.stats.entries)}`}
              />
              <Cell
                label="AVG CLASSIFIED POS"
                value={dec(driver.stats.avg_classified_position)}
                note="Incl. retirements — not finished races only"
              />
            </CellGrid>
            <CellGrid cols={6}>
              <Cell
                label="TOP-10 RATE"
                value={pct(driver.stats.top10_rate)}
                note={`${num(driver.stats.top10)} of ${num(driver.stats.entries)}`}
              />
              <Cell
                label="BEST CLASSIFIED POS"
                value={driver.stats.best_classified_position ? `P${driver.stats.best_classified_position}` : "—"}
                note="Highest classification recorded"
              />
              {/* These four were hardcoded "to be added" cells long after the
                  enrichment landed, so the page claimed the source had no
                  nationality, car number, qualifying or finishing status while
                  the API was returning all four. Each is now rendered from the
                  payload, and falls back to pending only when THIS driver has
                  no value -- which is a fact about the driver, not the schema. */}
              {driver.nationality ? (
                <Cell label="NATIONALITY" value={driver.nationality} note="From the drivers source" />
              ) : (
                <PendingCell label="NATIONALITY" why="No nationality recorded for this driver" />
              )}
              {driver.permanent_number !== null ? (
                <Cell
                  label="CAR NUMBER"
                  value={`#${driver.permanent_number}`}
                  note="Permanent number"
                />
              ) : (
                <PendingCell
                  label="CAR NUMBER"
                  why="Permanent numbers began in 2014; none recorded for this driver"
                />
              )}
              {/* Labelled QUALIFYING P1, never "poles". Counting fastest
                  qualifiers does not reproduce official pole tallies in the
                  sprint era, and the label has to say what was measured.

                  Three states, not two. This cell sits outside the `Async`
                  that gates the rest of the page, because it is a separate
                  request that resolves on its own schedule -- so "no data
                  yet" and "no data at all" arrive here as the same `null`.
                  Rendering the second while the first is true tells a reader
                  a driver has no qualifying record when the request simply
                  has not landed. Claiming an absence the data has not
                  established is the failure this project keeps a whole test
                  file about. */}
              {qualifying.loading ? (
                <Cell label="QUALIFYING P1" value="—" note="Loading…" />
              ) : qualifying.error ? (
                <Cell
                  label="QUALIFYING P1"
                  value="—"
                  note="Could not be loaded. This is a failed request, not an absence of data."
                />
              ) : qualifying.data && qualifying.data.qualifying_p1 !== null ? (
                <Cell
                  label="QUALIFYING P1"
                  value={num(qualifying.data.qualifying_p1)}
                  note={
                    qualifying.data.coverage_from
                      ? `Fastest-qualifier classifications, not official poles. Complete from ${qualifying.data.coverage_from}.`
                      : "Fastest-qualifier classifications, not official poles."
                  }
                />
              ) : (
                <PendingCell label="QUALIFYING P1" why="No qualifying rows recorded for this driver" />
              )}
              {driver.stats.dnf_rate !== null && driver.stats.dnf_rate !== undefined ? (
                <Cell
                  label="DNF RATE"
                  value={pct(driver.stats.dnf_rate)}
                  note={`${num(driver.stats.dnfs)} retirements in ${num(driver.stats.entries)} classifications`}
                />
              ) : (
                <PendingCell label="DNF RATE" why="Enrichment not loaded for this driver's races" />
              )}
            </CellGrid>

            <div className="panel--pad" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="kpi__label mono">TEAM TIMELINE</div>
              <div className="timeline">
                {Object.entries(
                  driver.constructors.reduce<Record<string, number[]>>((acc, spell) => {
                    (acc[spell.constructor_name] ??= []).push(spell.season);
                    return acc;
                  }, {}),
                ).map(([team, years]) => (
                  <div key={team} className="timeline__seg" style={{ flexGrow: years.length }} title={`${team} · ${seasonSpan(years)}`}>
                    {team} · {seasonSpan(years)}
                  </div>
                ))}
              </div>
            </div>
          </Panel>

          <SectionTitle aside={coverage}>Career charts</SectionTitle>
          <Async state={seasons} loadingRows={5}>
            {(rows) => (
              <div className="grid grid--2">
                <WinsBySeason data={rows} />
                <AvgPositionBySeason data={rows} />
              </div>
            )}
          </Async>

          <Panel>
            <PaneHead title="Career log · season by season" meta="R · W · P · WIN RATE · AVG P · BEST" />
          <Async state={seasons} loadingRows={5}>
            {(rows) => (
              <DataTable
                caption={`${driver.name} season-by-season record`}
                rows={rows}
                rowKey={(row) => row.season}
                emptyMessage="No seasons recorded for this driver."
                columns={[
                  {
                    key: "season",
                    header: "Season",
                    render: (row) => <Link to={`/seasons/${row.season}`} className="mono">{row.season}</Link>,
                  },
                  { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "wr", header: "Win rate", numeric: true, render: (r) => pct(r.win_rate) },
                  { key: "avg", header: "Avg class. pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
                  {
                    key: "best",
                    header: "Best class. pos",
                    numeric: true,
                    render: (r) => (r.best_classified_position ? `P${r.best_classified_position}` : "—"),
                  },
                  {
                    key: "dnf",
                    header: "DNF",
                    numeric: true,
                    // Was a hardcoded "n/a" citing a missing finishing-status
                    // column. `classification` is set on all 10,550 results,
                    // so every season block carries a real retirement count.
                    render: (r) =>
                      r.dnfs === null || r.dnfs === undefined ? (
                        <span className="pending mono" title="Enrichment not loaded for this season">n/a</span>
                      ) : (
                        <>{num(r.dnfs)}</>
                      ),
                  },
                ]}
              />
            )}
          </Async>
          </Panel>

          {/* Teammate record sits above constructor history: it is the closest
              thing this dataset has to a car-controlled comparison, so it is the
              most informative block on the page. */}
          <TeammateSection driverId={driver.id} driverName={driver.name} />

          <ConsistencySection entityId={driver.id} stats={driver.stats} />

          <CircuitStrengthSection driverId={driver.id} />

          <SectionTitle>Constructor history</SectionTitle>
          <DataTable
            caption={`Constructors ${driver.name} raced for`}
            rows={driver.constructors}
            rowKey={(row: ConstructorSpell) => `${row.season}-${row.constructor_id}`}
            emptyMessage="No constructor history recorded."
            columns={[
              { key: "season", header: "Season", render: (r) => <span className="mono">{r.season}</span> },
              {
                key: "team",
                header: "Constructor",
                render: (r) => <Link to={`/constructors/${r.constructor_slug}`}>{r.constructor_name}</Link>,
              },
              { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
              { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
              { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
            ]}
          />

        </>
      )}
    </Async>
  );
}
