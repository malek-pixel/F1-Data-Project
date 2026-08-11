import { Link } from "react-router-dom";
import { DataTable } from "./DataTable";
import { Async } from "./States";
import { dec, num, pct } from "./format";
import { Badge, SectionTitle, StatCard } from "./ui";
import { MethodologyNote } from "./MethodologyNote";
import { ChartFrame } from "../charts/Chart";
import { useApi } from "../hooks/useApi";
import type { Distribution, DriverCircuitsResponse, Stats } from "../types";

/**
 * Where a driver's results actually landed.
 *
 * A mean of P8 can describe a driver who is reliably eighth, or one who
 * alternates podiums with retirements. The histogram shows which, and the
 * mean/median gap quantifies it.
 */
function PositionHistogram({ dist }: { dist: Distribution }) {
  const max = Math.max(...dist.histogram.map((b) => b.count), 1);
  const width = 640;
  const rowHeight = 26;

  return (
    <ChartFrame
      title="Where results landed"
      unit="entries per finishing band"
      summary={
        `Distribution of ${dist.entries} classified finishes. ` +
        dist.histogram.map((b) => `${b.bucket}: ${b.count}`).join(", ") + "."
      }
      isEmpty={dist.entries === 0}
      table={
        <div className="table-scroll">
          <table className="data">
            <caption style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
              Classified position distribution
            </caption>
            <thead>
              <tr>
                <th scope="col">Band</th>
                <th scope="col" className="num">Entries</th>
                <th scope="col" className="num">Share</th>
              </tr>
            </thead>
            <tbody>
              {dist.histogram.map((b) => (
                <tr key={b.bucket}>
                  <td className="mono">{b.bucket}</td>
                  <td className="num">{b.count}</td>
                  <td className="num">{pct(b.share)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      }
    >
      {/* Horizontal bars: the band labels are text, so they read without rotation. */}
      <svg viewBox={`0 0 ${width} ${dist.histogram.length * rowHeight + 8}`} preserveAspectRatio="xMidYMid meet">
        {dist.histogram.map((bucket, index) => {
          const y = index * rowHeight + 4;
          const barWidth = (bucket.count / max) * (width - 150);
          return (
            <g key={bucket.bucket}>
              <text x="0" y={y + 14} fontSize="11" fill="#aab4c2" fontFamily="var(--mono)">
                {bucket.bucket}
              </text>
              <rect
                x="62"
                y={y + 3}
                width={Math.max(bucket.count > 0 ? 2 : 0, barWidth)}
                height="14"
                rx="2"
                fill={index <= 1 ? "#e10600" : index <= 3 ? "#0090ff" : "#3a4553"}
              >
                <title>{`${bucket.bucket}: ${bucket.count} entries (${(bucket.share * 100).toFixed(1)}%)`}</title>
              </rect>
              <text x={68 + barWidth} y={y + 14} fontSize="11" fill="#6f7a89" fontFamily="var(--mono)">
                {bucket.count}
              </text>
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

/**
 * Shared by driver and constructor pages -- the two are the same analysis over
 * a different entity, so they use one component rather than two that drift.
 */
export function ConsistencySection({
  entity = "drivers",
  entityId,
  stats,
}: {
  entity?: "drivers" | "constructors";
  entityId: number | string;
  stats: Stats;
}) {
  const state = useApi<Distribution>(`/${entity}/${entityId}/distribution`);

  return (
    <>
      <SectionTitle aside="DISTRIBUTION SHAPE">Consistency</SectionTitle>
      <Async state={state} loadingRows={4}>
        {(dist) => {
          const mean = stats.avg_classified_position;
          const gap = mean !== null && dist.median !== null ? mean - dist.median : null;
          return (
            <>
              <div className="grid grid--kpi" style={{ marginBottom: 16 }}>
                <StatCard label="MEAN" value={dec(mean)} note="Average classified position" />
                <StatCard label="MEDIAN" value={dec(dist.median, 1)} note="Middle result" />
                <StatCard
                  label="SPREAD (SD)"
                  value={dist.stdev === null ? "—" : dec(dist.stdev)}
                  note={dist.spread_reliable ? "Sample standard deviation" : "Too few entries to report"}
                  tone={dist.spread_reliable ? undefined : "warning"}
                />
                <StatCard label="TOP-10 RATE" value={pct(stats.top10_rate)} note={`${num(stats.top10)} of ${num(stats.entries)} entries`} />
                <StatCard label="WORST" value={dist.worst === null ? "—" : `P${dist.worst}`} />
              </div>

              {gap !== null && Math.abs(gap) >= 1 && (
                <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
                  <Badge tone="info">Reading this</Badge> The mean sits {dec(Math.abs(gap), 1)} positions{" "}
                  {gap > 0 ? "above" : "below"} the median
                  {gap > 0
                    ? ", which indicates a minority of much poorer classifications pulling the average up. The dataset has no finishing status, so it cannot attribute those to retirements."
                    : "."}
                </p>
              )}

              <PositionHistogram dist={dist} />
            </>
          );
        }}
      </Async>
    </>
  );
}

/** Circuits where a driver's record diverges most from their own career norm. */
export function CircuitStrengthSection({ driverId }: { driverId: number | string }) {
  const state = useApi<DriverCircuitsResponse>(`/drivers/${driverId}/circuits`);

  return (
    <>
      <SectionTitle aside="RELATIVE TO OWN CAREER AVERAGE">Circuit record</SectionTitle>
      <Async state={state} loadingRows={4}>
        {(data) => {
          const qualifying = data.circuits.filter((c) => c.meets_threshold);
          const ranked = [...qualifying].sort((a, b) => b.delta_vs_career - a.delta_vs_career);
          return (
            <>
              <MethodologyNote metric={data.methodology} />
              <DataTable
                caption="Per-circuit record against career average"
                rows={ranked.length > 0 ? ranked : data.circuits}
                rowKey={(row) => row.circuit_id}
                emptyMessage="No circuit appearances recorded."
                columns={[
                  {
                    key: "circuit",
                    header: "Circuit",
                    render: (r) => <Link to={`/circuits/${r.circuit_id}`}>{r.circuit_name}</Link>,
                  },
                  { key: "app", header: "Starts", numeric: true, render: (r) => num(r.appearances) },
                  { key: "wins", header: "Wins", numeric: true, render: (r) => num(r.wins) },
                  { key: "pod", header: "Podiums", numeric: true, render: (r) => num(r.podiums) },
                  { key: "avg", header: "Avg pos", numeric: true, render: (r) => dec(r.avg_classified_position) },
                  {
                    key: "delta",
                    header: "vs career",
                    numeric: true,
                    render: (r) => (
                      <span
                        className="mono"
                        style={{ color: r.delta_vs_career > 0 ? "var(--success)" : "var(--text-dim)" }}
                      >
                        {/* Sign plus wording, never colour alone. */}
                        {r.delta_vs_career > 0 ? "+" : ""}
                        {dec(r.delta_vs_career)}
                        {!r.meets_threshold && <span aria-label=" (below threshold)"> *</span>}
                      </span>
                    ),
                  },
                ]}
              />
              <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
                Positive means the driver was classified better here than their career average. Rows marked *
                fall below {data.min_appearances} appearances and are not treated as circuit specialism.
              </p>
            </>
          );
        }}
      </Async>
    </>
  );
}
