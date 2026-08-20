import { DataTable } from "../components/DataTable";
import { Link } from "react-router-dom";
import { Async } from "../components/States";
import { num, pct } from "../components/format";
import { Badge, CellGrid, PageHeader, PaneHead, Panel, PendingCell, SectionTitle } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import type { DatasetSummary, Era, MetricDoc, RecordEntry, SeasonRow } from "../types";

export function Records() {
  const coverage = useCoverage();
  const state = useApi<{ scope: string; records: RecordEntry[] }>("/records");
  return (
    <>
      <PageHeader
        eyebrow="RECORDS"
        title="Records"
        sub="Every record is calculated across the full dataset and states its own methodology."
      />
      <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
        <Badge tone="warning">Scope</Badge> {coverage} only. These are not all-time Formula 1 records — earlier
        results are outside the dataset.
      </p>
      <Async state={state} loadingRows={8}>
        {(payload) => {
          /* The mockup groups records into DRIVER / CONSTRUCTOR / CIRCUIT
             panels. The label the API already carries says which group a
             record belongs to, so the grouping needs no new field. */
          // Circuit- and season-scoped records are checked first: their labels
          // also end in "(driver)", so testing for the entity type alone would
          // sweep them into the driver group and leave the third panel empty.
          const scoped = (r: RecordEntry) => /circuit|season/i.test(r.record);
          const groups: [string, RecordEntry[]][] = [
            ["DRIVER RECORDS", payload.records.filter((r) => !scoped(r) && r.record.includes("(driver)"))],
            ["CONSTRUCTOR RECORDS", payload.records.filter((r) => !scoped(r) && r.record.includes("(constructor)"))],
            ["CIRCUIT & SEASON RECORDS", payload.records.filter(scoped)],
          ];
          return (
            <>
              {groups.map(([heading, records]) =>
                records.length === 0 ? null : (
                  <Panel key={heading}>
                    <PaneHead title={heading} meta={`${records.length} RECORDS · ${coverage}`} />
                    <div className="record-grid">
                      {records.map((record) => (
                        <div className="record" key={record.record}>
                          <div className="kpi__label mono">
                            {record.record.replace(/ \((driver|constructor)\)/, "").toUpperCase()}
                          </div>
                          <div className="record__row">
                            <span className="mono record__value">
                              {record.value < 1 ? `${(record.value * 100).toFixed(1)}%` : num(record.value)}
                            </span>
                            <span className="record__entity">{record.entity}</span>
                            {record.context && <Badge>{record.context}</Badge>}
                          </div>
                          <p className="kpi__note">{record.methodology}</p>
                        </div>
                      ))}
                    </div>
                  </Panel>
                ),
              )}

              {/* The mockup also lists most poles, most WCC titles and fewest
                  DNFs per race. This panel used to say the source had no
                  qualifying, points or finishing-status column and so could
                  never produce them. All three columns exist now -- 9,577
                  qualifying rows, points and classification on all 10,550
                  results -- so the honest statement is that these records are
                  not built yet, not that they are impossible. The distinction
                  matters: one is a backlog item, the other is a data limit. */}
              <Panel>
                <PaneHead title="RECORDS NOT BUILT YET" meta="DATA EXISTS · RECORD NOT IMPLEMENTED" />
                <CellGrid cols={3}>
                  <PendingCell
                    label="MOST QUALIFYING P1"
                    why="Qualifying is ingested and shown per driver; this dataset-wide record is not built yet"
                  />
                  <PendingCell
                    label="MOST WCC TITLES"
                    why="Points and standings exist; counting title-winning seasons is not built yet"
                  />
                  <PendingCell
                    label="FEWEST DNFs / RACE"
                    why="DNF rate is ingested and shown per driver; this dataset-wide record is not built yet"
                  />
                </CellGrid>
              </Panel>

              {/* Insights was removed; these two views are aggregate records
                  in their own right, so they live here rather than being
                  deleted along with the page that used to host them. */}
              <EraSection />
              <DominanceSection />
            </>
          );
        }}
      </Async>
    </>
  );
}

/**
 * Metric definitions strip (mockup § 09).
 *
 * Rendered from `/analytics/metrics` — the same registry the analytics code
 * computes from, so a definition here cannot drift from its implementation.
 */
function MetricDefinitions() {
  const state = useApi<{ metrics: MetricDoc[] }>("/analytics/metrics");
  return (
    <Panel>
      <PaneHead title="METRIC DEFINITIONS" meta="REPRODUCIBLE FROM THE DATASET" />
      <Async state={state} loadingRows={4}>
        {(payload) => (
          <div className="defs">
            {payload.metrics.map((metric) => (
              <div className="defs__item" key={metric.key}>
                <div className="mono defs__name">{metric.name.toUpperCase()}</div>
                <p className="defs__body">{metric.definition}</p>
                <p className="mono defs__formula">{metric.formula}</p>
              </div>
            ))}
          </div>
        )}
      </Async>
    </Panel>
  );
}

/**
 * Decade aggregates.
 *
 * Presented as periods, not a league table: regulations, calendar length and
 * field size all changed across these boundaries, so the rows are not
 * directly comparable with each other.
 */
function EraSection() {
  const state = useApi<{ eras: Era[]; caveat: string }>("/analytics/eras");
  return (
    <>
      <SectionTitle aside="PERIODS, NOT A RANKING">Eras</SectionTitle>
      <Async state={state} loadingRows={3}>
        {(data) => (
          <>
            <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
              <Badge tone="warning">Not equivalent</Badge> {data.caveat}
            </p>
            <div className="grid grid--2">
              {data.eras.map((era) => (
                <div className="card" key={era.decade}>
                  <div className="card__label mono">{era.label.toUpperCase()}</div>
                  <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 12 }}>
                    <span className="mono" style={{ fontSize: 13 }}>{era.seasons} seasons</span>
                    <span className="mono" style={{ fontSize: 13 }}>{era.races} races</span>
                    <span className="mono" style={{ fontSize: 13 }}>{era.drivers} drivers</span>
                    <span className="mono" style={{ fontSize: 13 }}>{era.constructors} teams</span>
                  </div>
                  <div className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)", marginBottom: 6 }}>
                    MOST RACE WINS IN PERIOD
                  </div>
                  {era.top_winners.map((winner) => (
                    <div key={winner.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, padding: "2px 0" }}>
                      <span>{winner.name}</span>
                      <span className="mono">{winner.wins}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </>
        )}
      </Async>
    </>
  );
}

/** How concentrated each season's wins were, across the whole dataset. */
function DominanceSection() {
  const state = useApi<{ seasons: SeasonRow[] }>("/analytics/dominance");
  return (
    <>
      <SectionTitle aside="WINS / RACES HELD">Season concentration over time</SectionTitle>
      <Async state={state} loadingRows={4}>
        {(data) => (
          <DataTable
            caption="Season concentration: race winners and leader win share"
            rows={data.seasons}
            rowKey={(row) => row.season}
            columns={[
              { key: "season", header: "Season", render: (r) => <Link to={`/seasons/${r.season}`} className="mono">{r.season}</Link> },
              { key: "races", header: "Races", numeric: true, render: (r) => r.races },
              { key: "dw", header: "Race winners", numeric: true, render: (r) => r.driver_winners },
              { key: "cw", header: "Winning teams", numeric: true, render: (r) => r.constructor_winners },
              { key: "share", header: "Leader win share", numeric: true, render: (r) => pct(r.top_driver_win_share, 0) },
              { key: "cshare", header: "Top team share", numeric: true, render: (r) => pct(r.top_constructor_win_share, 0) },
            ]}
          />
        )}
      </Async>
      <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
        Fewer distinct winners and a higher leader share indicate a more concentrated season. Normalised for
        calendar length; not normalised for grid size or regulation era.
      </p>
    </>
  );
}

export function Dataset() {
  const state = useApi<DatasetSummary>("/dataset/summary");
  return (
    <>
      <PageHeader
        eyebrow="DATA"
        title="Dataset Explorer"
        sub="What is in the source data, what is not, and where it is imperfect."
      />
      {/* How each number is defined belongs with the schema it is derived
          from. It moved here when the Insights page was removed. */}
      <MetricDefinitions />
      <Async state={state} loadingRows={8}>
        {(summary) => (
          <>
            <div className="grid grid--kpi">
              <div className="stat">
                <div className="stat__label mono">SOURCE</div>
                <div className="mono" style={{ fontSize: 14 }}>
                  {summary.source}
                </div>
              </div>
              <div className="stat">
                <div className="stat__label mono">COVERAGE</div>
                <div className="stat__value mono">
                  {summary.season_from}–{summary.season_to}
                </div>
              </div>
              <div className="stat">
                <div className="stat__label mono">TABLES</div>
                <div className="stat__value mono">{summary.tables.length}</div>
              </div>
            </div>

            <SectionTitle>Schema</SectionTitle>
            <div className="grid grid--2">
              {summary.tables.map((table) => (
                <div className="card" key={table.name}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <h3 className="card__title mono" style={{ marginBottom: 12 }}>
                      {table.name}
                    </h3>
                    <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>
                      {num(table.rows)} rows
                    </span>
                  </div>
                  <DataTable
                    caption={`Columns in ${table.name}`}
                    rows={table.columns}
                    rowKey={(row) => row.name}
                    columns={[
                      { key: "name", header: "Column", render: (r) => <span className="mono">{r.name}</span> },
                      { key: "type", header: "Type", render: (r) => <span className="mono">{r.type}</span> },
                      {
                        key: "null",
                        header: "Nullable",
                        render: (r) => (r.nullable ? "yes" : "no"),
                      },
                    ]}
                  />
                </div>
              ))}
            </div>

            <SectionTitle>Field availability</SectionTitle>
            <div className="grid grid--2">
              <div className="card">
                <div className="card__label mono">PRESENT IN SOURCE</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {summary.available_fields.map((field) => (
                    <span key={field} className="badge" style={{ color: "var(--success)", borderColor: "rgba(34,197,94,.3)", background: "rgba(34,197,94,.1)" }}>
                      {field}
                    </span>
                  ))}
                </div>
              </div>
              <div className="card">
                <div className="card__label mono">ABSENT FROM SOURCE</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {summary.unavailable_fields.map((field) => (
                    <Badge key={field} tone="warning">
                      {field}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>

            <SectionTitle>Known issues</SectionTitle>
            <div className="card">
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {summary.known_issues.map((issue) => (
                  <li key={issue} style={{ fontSize: 13, color: "var(--text-dim)", marginBottom: 8 }}>
                    {issue}
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </Async>
    </>
  );
}
