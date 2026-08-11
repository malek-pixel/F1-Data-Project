import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AvgPositionBySeason, WinsBySeason } from "../charts/SeasonCharts";
import { DriverContributionChart } from "../charts/ContributionChart";
import { DataTable } from "../components/DataTable";
import { StatBlock } from "../components/StatBlock";
import { ConsistencySection } from "../components/Consistency";
import { Async, Unavailable } from "../components/States";
import { dec, num, pct, seasonSpan } from "../components/format";
import { Badge, PageHeader, SectionTitle, Tabs } from "../components/ui";
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
          <PageHeader
            eyebrow="CONSTRUCTOR"
            title={team.name}
            sub={`${seasonSpan(team.seasons.map((s) => s.season))} · ${team.seasons.length} seasons in dataset`}
          />

          <StatBlock stats={team.stats} />

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
            <Badge tone="info">Methodology</Badge> Share of this constructor&rsquo;s own results, not share of
            championship points — the source data has no points column.
          </p>

          <Async state={contribution} loadingRows={3}>
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
                        render: (row) => <Link to={`/drivers/${row.driver_id}`}>{row.driver_name}</Link>,
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
            <Unavailable label="CONSTRUCTORS' POINTS" why="No points column in results.csv." />
            <Unavailable label="CHAMPIONSHIP TITLES" why="Titles require points; not derivable from classifications." />
            <Unavailable label="RELIABILITY / DNFs" why="No finishing-status column." />
            <Unavailable label="CAR SPECIFICATIONS" why="No car metadata in the dataset." />
          </div>
        </>
      )}
    </Async>
  );
}
