import { Link } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Async } from "../components/States";
import { dec, num } from "../components/format";
import { Badge, PageHeader, SectionTitle, StatCard } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { count, useCoverage, useDataset } from "../hooks/useDataset";
import type { DatasetSummary, Health, Insight, SeasonSummary } from "../types";

/** Card copy is a function of live dataset counts -- never a hardcoded figure. */
const entryPoints = (info: Health | null) => [
  {
    to: "/drivers",
    label: "Driver Explorer",
    body: `${count(info?.drivers, "drivers")}. Career records, season trends, head-to-head.`,
  },
  {
    to: "/constructors",
    label: "Constructor Explorer",
    body: `${count(info?.constructors, "constructors")}. Season form and driver contribution.`,
  },
  {
    to: "/circuits",
    label: "Circuit Explorer",
    // Only some circuits ship a track-map SVG, so the count of circuits and the
    // count of maps are different numbers. Stating one as the other would be
    // the kind of quiet overclaim this project exists to avoid.
    body: `${count(info?.circuits, "circuits")}, ${info?.circuits_with_map ?? "—"} with track maps. Historical winners and specialists.`,
  },
  { to: "/records", label: "Records", body: "Dataset-wide records, each with its methodology stated." },
];

export function Home() {
  const info = useDataset();
  const coverage = useCoverage();
  const health = useApi<Health>("/health");
  const dataset = useApi<DatasetSummary>("/dataset/summary");
  // "Latest available season" -- resolved from the data, never hardcoded.
  const latest = health.data?.season_to;
  const season = useApi<SeasonSummary>(latest ? `/seasons/${latest}` : null);
  const insights = useApi<{ insights: Insight[] }>("/insights?limit=3");

  return (
    <>
      <PageHeader
        eyebrow="OVERVIEW"
        title="F1 Stats"
        sub={`Formula 1 race classifications, ${coverage}. An analyst tool over a static historical dataset.`}
      />

      <Async state={health} loadingRows={2}>
        {(info) => (
          <div className="grid grid--kpi">
            <StatCard label="SEASONS" value={`${info.season_from}–${info.season_to}`} />
            <StatCard label="RACES" value={num(info.races)} />
            <StatCard label="CLASSIFICATIONS" value={num(info.results)} note="One row per driver per race" />
            <StatCard label="DATA MODE" value="Static" note="Historical dataset — not live timing" />
          </div>
        )}
      </Async>

      <SectionTitle aside={latest ? `LATEST SEASON IN DATASET · ${latest}` : undefined}>
        {latest ? `${latest} season` : "Latest season"}
      </SectionTitle>
      <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
        <Badge tone="warning">Not championship standings</Badge> Ranked by wins, then podiums, then average
        classified position — the dataset carries no points column.
      </p>

      <Async state={season} loadingRows={6}>
        {(summary) => (
          <div className="grid grid--2">
            <div className="card">
              <div className="card__label mono">DRIVERS · BY WINS</div>
              <DataTable
                caption={`${summary.season} drivers ranked by wins`}
                rows={summary.drivers.slice(0, 10)}
                rowKey={(row) => row.id}
                columns={[
                  { key: "name", header: "Driver", render: (r) => <Link to={`/drivers/${r.id}`}>{r.name}</Link> },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "avg", header: "Avg pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
                ]}
              />
            </div>
            <div className="card">
              <div className="card__label mono">CONSTRUCTORS · BY WINS</div>
              <DataTable
                caption={`${summary.season} constructors ranked by wins`}
                rows={summary.constructors.slice(0, 10)}
                rowKey={(row) => row.id}
                columns={[
                  {
                    key: "name",
                    header: "Constructor",
                    render: (r) => <Link to={`/constructors/${r.id}`}>{r.name}</Link>,
                  },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "podiums", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "avg", header: "Avg pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
                ]}
              />
            </div>
          </div>
        )}
      </Async>

      <SectionTitle>Explore</SectionTitle>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
        {entryPoints(info).map((entry) => (
          <Link key={entry.to} to={entry.to} className="card">
            <h3 className="card__title" style={{ marginBottom: 6 }}>
              {entry.label}
            </h3>
            <p style={{ fontSize: 13, color: "var(--text-dim)", margin: 0 }}>{entry.body}</p>
          </Link>
        ))}
      </div>

      <SectionTitle aside="CALCULATED">Insights</SectionTitle>
      <Async state={insights} loadingRows={3}>
        {(payload) => (
          <div className="grid grid--2">
            {payload.insights.map((insight) => (
              <div className="card" key={insight.headline}>
                <h3 className="card__title" style={{ fontSize: 15 }}>
                  {insight.headline}
                </h3>
                <p style={{ fontSize: 13, color: "var(--text-dim)", margin: 0 }}>{insight.detail}</p>
              </div>
            ))}
          </div>
        )}
      </Async>

      <SectionTitle>What this dataset cannot tell you</SectionTitle>
      <Async state={dataset} loadingRows={2}>
        {(summary) => (
          <div className="card">
            <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
              These fields are absent from the source. Nothing in this tool estimates them.
            </p>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
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
          </div>
        )}
      </Async>
    </>
  );
}
