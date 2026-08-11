import { DataTable } from "../components/DataTable";
import { Link } from "react-router-dom";
import { Async } from "../components/States";
import { num, pct } from "../components/format";
import { Badge, CellGrid, PageHeader, PaneHead, Panel, PendingCell, SectionTitle } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import type { DatasetSummary, Era, Insight, RecordEntry, SeasonRow } from "../types";

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

              {/* The mockup also lists most poles, most WCC titles and
                  fewest DNFs per race. Each needs a column the source does
                  not have, so each keeps its slot and says so. */}
              <Panel>
                <PaneHead title="RECORDS THIS DATASET CANNOT PRODUCE" meta="WOULD NEED NEW SOURCE COLUMNS" />
                <CellGrid cols={3}>
                  <PendingCell label="MOST POLES" why="No qualifying or grid column in the source" />
                  <PendingCell label="MOST WCC TITLES" why="Titles require a points column" />
                  <PendingCell label="FEWEST DNFs / RACE" why="No finishing-status column in the source" />
                </CellGrid>
              </Panel>
            </>
          );
        }}
      </Async>
    </>
  );
}

export function Insights() {
  const state = useApi<{ insights: Insight[] }>("/insights?limit=12");
  return (
    <>
      <PageHeader
        eyebrow="INSIGHTS"
        title="Insights"
        sub="Observations derived from the data. Each states the query it came from."
      />
      <p style={{ fontSize: 13, color: "var(--text-dim)" }}>
        <Badge tone="info">Descriptive only</Badge> These describe what the results record, never why. The dataset
        contains no explanatory variables — no car data, no reliability, no team budgets — so no causal claim can be
        supported.
      </p>
      <SectionTitle aside="CALCULATED FROM THE DATASET">Observations</SectionTitle>
      <Async state={state} loadingRows={6}>
        {(payload) => (
          <div className="grid grid--2">
            {payload.insights.map((insight) => (
              <div className="card" key={insight.headline}>
                <div className="card__label mono">{insight.kind.replace("_", " ").toUpperCase()}</div>
                <h3 className="card__title" style={{ fontSize: 16, marginBottom: 8 }}>
                  {insight.headline}
                </h3>
                <p style={{ fontSize: 13, color: "var(--text-dim)", margin: "0 0 10px" }}>{insight.detail}</p>
                <p style={{ fontSize: 12, color: "var(--text-faint)", margin: 0 }}>
                  <strong>Basis:</strong> {insight.basis}
                </p>
              </div>
            ))}
          </div>
        )}
      </Async>

      <EraSection />
      <DominanceSection />
    </>
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

/**
 * Car Library.
 *
 * The design specifies this page, and there is no car data of any kind in the
 * source. Rather than invent chassis, engine or performance figures, the page
 * ships as an honest empty shell that documents the schema real data would
 * populate.
 */
export function CarLibrary() {
  return (
    <>
      <PageHeader
        eyebrow="LIBRARIES"
        title="Cars"
        sub="Car specifications are not part of the current dataset."
      />

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
          <Badge tone="warning">No data source</Badge>
          <strong style={{ fontSize: 15 }}>This section has no backing data.</strong>
        </div>
        <p style={{ fontSize: 14, color: "var(--text-dim)", maxWidth: "72ch" }}>
          The source (<code style={{ fontFamily: "var(--mono)" }}>results.csv</code>) contains race
          classifications only — season, round, race, date, position, driver and constructor. It carries no chassis
          designations and no car specifications. Rather than populate this page with figures sourced from
          elsewhere and presented as if they came from the dataset, it stays empty until a real car dataset is added.
        </p>
        <p style={{ fontSize: 14, color: "var(--text-dim)", maxWidth: "72ch" }}>
          Constructor performance by season <em>is</em> available and is the closest supported equivalent — see any
          constructor page.
        </p>
      </div>

      <Panel>
        <PaneHead title="Fields a car dataset would provide" meta="ALL PENDING — NO CAR SOURCE" />
        <CellGrid cols={3}>
          <PendingCell label="CHASSIS" why="No chassis-designation column" />
          <PendingCell label="CONSTRUCTOR · ENGINE" why="No power-unit column" />
          <PendingCell label="SEASON" why="Would come with a chassis table" />
          <PendingCell label="POWER" why="Not published in a machine-readable public dataset" />
          <PendingCell label="WEIGHT" why="No car metadata in the dataset" />
          <PendingCell label="AERO CONFIGURATION" why="No car metadata in the dataset" />
        </CellGrid>
        <CellGrid cols={3}>
          <PendingCell label="FASTEST LAPS" why="No fastest-lap column in the source" />
          <PendingCell label="POINTS" why="No points column in the source" />
          <PendingCell label="RELIABILITY" why="Needs finishing status; retirements are ranked, not flagged" />
        </CellGrid>
      </Panel>

      {/* The mockup's chassis table, with the columns it would carry. It is
          rendered as an empty table rather than omitted, so the shape of the
          missing data is visible. */}
      <Panel>
        <PaneHead title="Chassis table" meta="0 ROWS — AWAITING A CAR DATASET" />
        <div className="table-scroll">
          <table className="data">
            <caption
              style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}
            >
              Chassis table, empty pending a car dataset
            </caption>
            <thead>
              <tr>
                {["Chassis", "Constructor · engine", "Season", "Drivers", "W", "Podiums", "Poles", "FL", "Pts", "Reliability"].map(
                  (header) => (
                    <th key={header} scope="col">
                      {header}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={10} className="table-empty">
                  No chassis rows. The source carries race classifications only — adding a car dataset fills this
                  table without reshaping any existing one.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Panel>

      <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 24, maxWidth: "72ch" }}>
        The database schema is designed so a <code style={{ fontFamily: "var(--mono)" }}>cars</code> table keyed on
        constructor and season can be added without reshaping existing tables.
      </p>
    </>
  );
}
