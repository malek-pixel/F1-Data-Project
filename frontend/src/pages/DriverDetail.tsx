import { Link, useParams } from "react-router-dom";
import { AvgPositionBySeason, WinsBySeason } from "../charts/SeasonCharts";
import { DataTable } from "../components/DataTable";
import { TeammateSection } from "../components/Teammates";
import { CircuitStrengthSection, ConsistencySection } from "../components/Consistency";
import { Async } from "../components/States";
import { dec, num, pct, seasonSpan } from "../components/format";
import { Cell, CellGrid, PaneHead, Panel, PendingCell, SectionTitle } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import type { ConstructorSpell, DriverDetail as Detail, SeasonStats } from "../types";

export function DriverDetail() {
  const { id } = useParams();
  const coverage = useCoverage();
  const detail = useApi<Detail>(`/drivers/${id}`);
  const seasons = useApi<SeasonStats[]>(`/drivers/${id}/seasons`);

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
                <Link className="btn" to={`/compare?kind=drivers&left=${driver.id}`}>
                  Compare
                </Link>
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
              <PendingCell label="NATIONALITY" why="Needs Ergast drivers.csv; not in results.csv" />
              <PendingCell label="CAR NUMBER" why="No car-number column in the source" />
              <PendingCell label="POLE RATE" why="No qualifying or grid column in the source" />
              <PendingCell label="DNF RATE" why="No finishing-status column; retirements are ranked, not flagged" />
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
                    render: () => <span className="pending mono" title="No finishing-status column in the source">n/a</span>,
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
                render: (r) => <Link to={`/constructors/${r.constructor_id}`}>{r.constructor_name}</Link>,
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
