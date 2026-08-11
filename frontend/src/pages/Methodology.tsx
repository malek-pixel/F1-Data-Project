import { Badge, PageHeader, PaneHead, Panel, SectionTitle } from "../components/ui";
import { useCoverage, useDataset } from "../hooks/useDataset";
import { useApi } from "../hooks/useApi";
import { Async } from "../components/States";
import type { Health, MetricDoc } from "../types";

/**
 * Methodology page.
 *
 * Content mirrors METHODOLOGY.md. The mockup's version of this screen
 * describes a nightly Ergast ingest into a DuckDB warehouse with grid
 * position and fastest lap present -- that was written against sample data.
 * The layout is kept; the content states the real pipeline.
 */

/** Built from live dataset counts so the page cannot describe a stale corpus. */
const pipeline = (info: Health | null) => [
  {
    step: "01 · SOURCE",
    title: "results.csv",
    body: info
      ? `${info.results.toLocaleString()} race classifications, ${info.season_from}–${info.season_to}. Seven columns.`
      : "Race classifications from a single seven-column CSV.",
  },
  { step: "02 · VALIDATE", title: "Fail loudly", body: "Types, ranges, duplicates, date/season agreement, circuit-map coverage. Fatal issues abort the build." },
  { step: "03 · NORMALIZE", title: "Stable IDs", body: "Integer keys for drivers, constructors, circuits and races. Circuit resolved from race name." },
  { step: "04 · LOAD", title: "SQLite", body: "Indexed relational schema, rebuilt from scratch on every run." },
  { step: "05 · SERVE", title: "Read-only API", body: "Every metric computed in one analytics module. Connections open read-only." },
];


/**
 * Metric definitions, read from the backend registry rather than restated here.
 *
 * The same objects are shown inline beside the numbers they describe, so the
 * published methodology and the implemented calculation cannot drift apart.
 */
function MetricRegistry() {
  const state = useApi<{ thresholds: Record<string, number>; metrics: MetricDoc[] }>("/analytics/metrics");
  return (
    <>
      <SectionTitle aside="SERVED FROM THE ANALYTICS LAYER">Metric definitions</SectionTitle>
      <Async state={state} loadingRows={6}>
        {(data) => (
          <>
            <div className="grid grid--2">
              {data.metrics.map((metric) => (
                <div className="card" key={metric.key}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <h3 className="card__title" style={{ fontSize: 16, margin: 0 }}>
                      {metric.name}
                    </h3>
                    <span className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)" }}>
                      {metric.level.toUpperCase()}
                    </span>
                  </div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--info)", margin: "8px 0 10px" }}>
                    {metric.formula}
                  </div>
                  <p style={{ fontSize: 13, color: "var(--text-dim)", margin: "0 0 10px" }}>{metric.definition}</p>
                  <dl style={{ margin: 0, display: "grid", gap: 6 }}>
                    <div>
                      <dt className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)" }}>
                        EDGE CASES
                      </dt>
                      <dd style={{ margin: 0, fontSize: 12, color: "var(--text-dim)" }}>{metric.edge_cases}</dd>
                    </div>
                    <div>
                      <dt className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--warning)" }}>
                        LIMITATIONS
                      </dt>
                      <dd style={{ margin: 0, fontSize: 12, color: "var(--text-dim)" }}>{metric.limitations}</dd>
                    </div>
                  </dl>
                  {metric.min_sample !== null && (
                    <p className="mono" style={{ fontSize: 11, color: "var(--text-faint)", margin: "10px 0 0" }}>
                      MINIMUM SAMPLE · {metric.min_sample}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 12 }}>
              Thresholds differ by metric and are chosen from this dataset's distribution:{" "}
              {Object.entries(data.thresholds)
                .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`)
                .join(" · ")}
              .
            </p>
          </>
        )}
      </Async>
    </>
  );
}

export function Methodology() {
  const info = useDataset();
  const coverage = useCoverage();
  const PIPELINE = pipeline(info);

  return (
    <>
      <PageHeader
        eyebrow="METHODOLOGY"
        title="Methodology"
        sub="What every number means, how it is calculated, and what the dataset cannot support."
      />

      {/* Mockup section 12: the pipeline reads as connected steps with arrows
          between them, not as detached cards. */}
      <Panel pad>
        <PaneHead flush title="Data pipeline" meta="REPRODUCIBLE FROM A CLEAN CLONE" />
        <ol className="pipeline">
          {PIPELINE.map((stage, index) => (
            <li className="pipeline__step" key={stage.step}>
              <div className={`pipeline__card${index === PIPELINE.length - 1 ? " pipeline__card--end" : ""}`}>
                <div className="mono pipeline__n">{stage.step}</div>
                <div className="pipeline__title">{stage.title}</div>
                <div className="pipeline__body">{stage.body}</div>
              </div>
              {index < PIPELINE.length - 1 && (
                <span className="pipeline__arrow mono" aria-hidden="true">
                  &rarr;
                </span>
              )}
            </li>
          ))}
        </ol>
      </Panel>

      {/* Mockup section 12: field availability by season. The design shows a
          three-state matrix (present / partial / missing). This dataset has no
          partial case -- a column is in all 26 seasons or in none -- so the
          matrix is honest at two states rather than inventing a third. */}
      <Panel pad>
        <PaneHead
          flush
          title="Field availability by season"
          meta={`GREEN = PRESENT · RED = ABSENT · ${coverage}`}
        />
        <div className="matrix">
          {(
            [
              ["Race classification", true],
              ["Driver", true],
              ["Constructor", true],
              ["Circuit (derived)", true],
              ["Race date", true],
              ["Grid position", false],
              ["Qualifying", false],
              ["Fastest lap", false],
              ["Championship points", false],
              ["Finishing status", false],
              ["Pit stops", false],
              ["Lap-by-lap timing", false],
              ["Sprint results", false],
              ["Telemetry / tyres", false],
            ] as [string, boolean][]
          ).map(([field, present]) => (
            <div className="matrix__row" key={field}>
              <div className="matrix__label">{field}</div>
              {Array.from({ length: (info?.seasons ?? 26) as number }, (_unused, i) => (
                <div
                  key={i}
                  className={`matrix__dot matrix__dot--${present ? "yes" : "no"}`}
                  title={`${field} · ${(info?.season_from ?? 2000) + i} · ${present ? "present" : "absent"}`}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="kpi__note" style={{ marginTop: 12 }}>
          Availability is uniform across the covered seasons: the source is one CSV with seven columns, so a field
          is either in every season or in none. Nothing here is partial, and nothing is inferred.
        </p>
      </Panel>

      <SectionTitle>The one thing to understand first</SectionTitle>
      <div className="card">
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
          <Badge tone="warning">Classification, not finishing status</Badge>
        </div>
        <p className="prose" style={{ margin: 0 }}>
          The <code>position</code> column holds final classification order, 1..N. There is no{" "}
          <code>DNF</code>, <code>DNS</code>, <code>DSQ</code> or <code>status</code> column anywhere in the source.
          A driver who retired on lap 1 still receives a classification number. This application therefore cannot
          distinguish a finish from a retirement, and every metric derived from position is named as a metric about
          classification.
        </p>
      </div>

      <MetricRegistry />

      <SectionTitle>Handling of edge cases</SectionTitle>
      <div className="card prose">
        <h3>Small samples</h3>
        <p>
          Rates computed from fewer than 10 entries are returned with a reliability flag and marked in the UI, rather
          than hidden. A driver with 2 entries and 1 win genuinely has a 50% win rate; the flag makes the sample size
          visible. Rate-based <em>records</em> apply the threshold as a hard filter, so a single-race driver cannot
          top the win-rate table.
        </p>
        <h3>Zero versus no data</h3>
        <p>
          A rate is null when there are no entries and 0 when there are entries but no wins. These are different
          facts and the UI renders them differently — an em dash for the former, 0.0% for the latter. Win share is
          null when a constructor never won, never 0%, which would imply a share of a real total.
        </p>
        <h3>Season rankings</h3>
        <p>
          Season tables rank by wins, then podiums, then average classified position. They are <strong>not</strong>{" "}
          championship standings and are labelled as such everywhere they appear. Reproducing official standings
          requires a points column, which the source does not have.
        </p>
        <h3>Circuit identity</h3>
        <p>
          The source has no circuit column, only race name — which is not a stable circuit key. The European, German,
          French, Japanese and United States Grands Prix all changed venue inside the {coverage} window. Circuits are
          resolved through a curated season-aware map committed alongside the ETL, and the build fails if any race
          name has no matching rule. This map encodes external knowledge, not data from the source, and should be
          reviewed when a season is added.
        </p>
      </div>

      <SectionTitle>Known limitations</SectionTitle>
      <div className="card prose">
        <ul>
          <li>Coverage is {coverage} only. No record here is an all-time Formula 1 record.</li>
          <li>Season lengths vary from 16 to 24 races, so cross-era season totals are not normalised.</li>
          <li>
            The 2002 French Grand Prix carries 20 classification rows but runs to P22 — two rows are absent upstream.
            Denominators count rows present, never the maximum position, so this understates that race's field size
            rather than inventing entries.
          </li>
          <li>
            Constructor identity follows the source's naming. Distinct historical constructors are never merged
            without evidence — Sauber, BMW Sauber and Alfa Romeo remain separate entities.
          </li>
          <li>The data is static. Nothing in this tool is live, and no page implies an in-progress race.</li>
        </ul>
      </div>
    </>
  );
}
