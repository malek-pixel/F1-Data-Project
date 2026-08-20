import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AvgPositionBySeason, WinsBySeason } from "../charts/SeasonCharts";
import { DriverContributionChart } from "../charts/ContributionChart";
import { DataTable } from "../components/DataTable";
import { ConsistencySection } from "../components/Consistency";
import { Async, Unavailable } from "../components/States";
import { teamLogo } from "../components/teamLogo";
import { dec, num, pct, seasonSpan } from "../components/format";
import { Badge, Cell, CellGrid, Panel, PendingCell, SectionTitle, Tabs } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import { qs } from "../services/api";
import type { ConstructorDetail as Detail, DriverContribution } from "../types";

type Metric = "entry_share" | "win_share" | "podium_share";

export function ConstructorDetail() {
  const { id } = useParams();
  const [metric, setMetric] = useState<Metric>("win_share");
  const [season, setSeason] = useState<number | "">("");

  const coverage = useCoverage();
  const detail = useApi<Detail>(`/constructors/${id}`);
  const contribution = useApi<DriverContribution[]>(
    `/constructors/${id}/drivers${qs({ season: season || undefined })}`,
  );

  return (
    <Async state={detail} loadingRows={6}>
      {(team) => (
        <>
          {/* Mockup § 04: masthead plus a measured strip. The design's
              POINTS, TITLES, BASE and LIVERY cells keep their place and state
              that the source cannot fill them. */}
          <Panel>
            <div className="entity-head">
              <div>
                <div className="entity-head__eyebrow mono">CONSTRUCTOR</div>
                <h1 className="entity-head__name">{team.name}</h1>
                <div className="entity-head__sub">
                  {seasonSpan(team.seasons.map((s) => s.season))} · {team.seasons.length} seasons in dataset
                </div>
              </div>
              <div className="entity-head__actions">
                <Link className="btn" to={`/compare?kind=constructors&left=${team.slug}`}>
                  Compare
                </Link>
                {/* Mockup § 07 hangs a car gallery off the team page. */}
                <Link className="btn" to={`/cars?team=${encodeURIComponent(team.name)}`}>
                  Cars
                </Link>
                {teamLogo(team.name) ? (
                  <div className="entity-head__portrait gallery__media gallery__media--logo">
                    <img src={teamLogo(team.name)!} alt="" decoding="async" width={320} height={320} />
                  </div>
                ) : (
                  <div className="entity-head__portrait gallery__media mono">
                    LIVERY
                    <span>to be added</span>
                  </div>
                )}
              </div>
            </div>

            <CellGrid cols={6}>
              <Cell label="ENTRIES" value={num(team.stats.entries)} note="Car-races, not races" />
              <Cell label="WINS" value={num(team.stats.wins)} />
              <Cell label="PODIUMS" value={num(team.stats.podiums)} note="Classified P1–P3" />
              <Cell label="WIN RATE" value={pct(team.stats.win_rate)} note="wins / entries" />
              <Cell
                label="AVG CLASSIFIED POS"
                value={dec(team.stats.avg_classified_position)}
                note="Incl. retirements"
              />
              <Cell
                label="BEST CLASSIFIED POS"
                value={team.stats.best_classified_position ? `P${team.stats.best_classified_position}` : "—"}
              />
            </CellGrid>
            <CellGrid cols={4}>
              <Cell label="POINTS" value={dec(team.stats.points)} note="All seasons, incl. sprints" />
              {/* Titles need a season-by-season champion, which is a
                  derivation over standings this app does not yet make.
                  Points themselves are available and shown alongside. */}
              <PendingCell label="WCC TITLES" why="Not derived: needs a champion per season, not just points" />
              <PendingCell label="BASE" why="Needs Ergast constructors.csv" />
              <PendingCell label="LIVERY" why="No livery or colour data in the source" />
            </CellGrid>
          </Panel>

          <SectionTitle aside={coverage}>Performance over time</SectionTitle>
          <div className="grid grid--2">
            <WinsBySeason data={team.seasons} />
            <AvgPositionBySeason data={team.seasons} />
          </div>

          <SectionTitle>Driver contribution</SectionTitle>
          <div className="controls">
            <Tabs
              label="Contribution metric"
              active={metric}
              onChange={setMetric}
              tabs={[
                { id: "win_share", label: "Wins" },
                { id: "podium_share", label: "Podiums" },
                { id: "entry_share", label: "Entries" },
              ]}
            />
            <div className="field">
              <label htmlFor="contrib-season">SEASON</label>
              <select
                id="contrib-season"
                className="select"
                value={season}
                onChange={(event) => setSeason(event.target.value ? Number(event.target.value) : "")}
              >
                <option value="">All seasons</option>
                {team.seasons.map((row) => (
                  <option key={row.season} value={row.season}>
                    {row.season}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
            <Badge tone="info">Methodology</Badge> Share of this constructor&rsquo;s own results (entries,
            wins, podiums), not share of championship points. Points exist in the dataset; a points
            share is simply a different question from the results share shown here.
          </p>

          <Async state={contribution} loadingRows={3} loadingVariant="chart">
            {(rows) => (
              <div className="grid grid--2">
                <DriverContributionChart rows={rows} metric={metric} />
                <div className="card">
                  <div className="card__label mono">DRIVER BREAKDOWN</div>
                  <DataTable
                    caption={`${team.name} driver breakdown`}
                    rows={rows}
                    rowKey={(row) => row.driver_id}
                    emptyMessage="No drivers recorded for this selection."
                    columns={[
                      {
                        key: "driver",
                        header: "Driver",
                        render: (row) => <Link to={`/drivers/${row.driver_slug}`}>{row.driver_name}</Link>,
                      },
                      { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
                      { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                      { key: "share", header: "Win share", numeric: true, render: (r) => pct(r.win_share) },
                      {
                        key: "avg",
                        header: "Avg class. pos",
                        numeric: true,
                        render: (r) => dec(r.avg_classified_position),
                      },
                    ]}
                  />
                </div>
              </div>
            )}
          </Async>

          <ConsistencySection entity="constructors" entityId={team.id} stats={team.stats} />

          <SectionTitle>Season record</SectionTitle>
          <DataTable
            caption={`${team.name} season-by-season record`}
            rows={team.seasons}
            rowKey={(row) => row.season}
            columns={[
              {
                key: "season",
                header: "Season",
                render: (row) => <Link to={`/seasons/${row.season}`} className="mono">{row.season}</Link>,
              },
              { key: "entries", header: "Entries", numeric: true, render: (r) => num(r.entries) },
              { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
              { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
              { key: "avg", header: "Avg class. pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
            ]}
          />

          <SectionTitle>Not available for this constructor</SectionTitle>
          <div className="grid grid--kpi">
            {/* Points and DNFs were listed here as unavailable long after
                they were ingested, so this panel told users a column was
                missing while the API served it. Both are now shown in the
                stat block above; only genuinely sourceless things remain. */}
            <Unavailable label="CHAMPIONSHIP TITLES" why="Not derived: needs a champion per season, not just points." />
            <Unavailable label="CAR SPECIFICATIONS" why="No source supplies chassis or engine detail." />
            <Unavailable label="FASTEST LAPS" why="No source records the fastest lap of a race." />
            <Unavailable label="LIVERY" why="No source supplies livery or colour data." />
          </div>
        </>
      )}
    </Async>
  );
}
