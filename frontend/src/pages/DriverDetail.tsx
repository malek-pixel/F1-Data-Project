import { Link, useParams } from "react-router-dom";
import { AvgPositionBySeason, WinsBySeason } from "../charts/SeasonCharts";
import { DataTable } from "../components/DataTable";
import { StatBlock, UnavailableMetrics } from "../components/StatBlock";
import { TeammateSection } from "../components/Teammates";
import { CircuitStrengthSection, ConsistencySection } from "../components/Consistency";
import { Async } from "../components/States";
import { dec, num, pct, seasonSpan } from "../components/format";
import { PageHeader, SectionTitle } from "../components/ui";
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
          <PageHeader
            eyebrow="DRIVER"
            title={driver.name}
            sub={
              <>
                {seasonSpan(driver.constructors.map((spell) => spell.season))} ·{" "}
                {[...new Set(driver.constructors.map((s) => s.constructor_name))].join(" · ")}
              </>
            }
          />

          <StatBlock stats={driver.stats} />

          <SectionTitle aside={coverage}>Career charts</SectionTitle>
          <Async state={seasons} loadingRows={5}>
            {(rows) => (
              <div className="grid grid--2">
                <WinsBySeason data={rows} />
                <AvgPositionBySeason data={rows} />
              </div>
            )}
          </Async>

          <SectionTitle>Season by season</SectionTitle>
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
                ]}
              />
            )}
          </Async>

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

          <SectionTitle>Not available for this driver</SectionTitle>
          <UnavailableMetrics />
        </>
      )}
    </Async>
  );
}
