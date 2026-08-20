import type { SeasonStats } from "../types";
import { dec } from "../components/format";
import { AXIS, ChartFrame, TICK, labelEvery, ticks } from "./Chart";
import { SERIES } from "./palette";

const W = 760;
const H = 240;
const PAD = { top: 12, right: 12, bottom: 34, left: 40 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

const SR_ONLY = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" } as const;

function DataTable({
  rows,
  valueHeader,
  value,
  caption,
}: {
  rows: SeasonStats[];
  valueHeader: string;
  value: (r: SeasonStats) => string;
  caption: string;
}) {
  return (
    <div className="table-scroll">
      <table className="data">
        <caption style={SR_ONLY}>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Season</th>
            <th scope="col" className="num">{valueHeader}</th>
            <th scope="col" className="num">Entries</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.season}>
              <td className="mono">{row.season}</td>
              <td className="num">{value(row)}</td>
              <td className="num">{row.entries}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Wins by season. Bars, because seasons are discrete categories being
 * compared -- not a continuous trend.
 */
export function WinsBySeason({ data, color = SERIES[0] }: { data: SeasonStats[]; color?: string }) {
  const max = Math.max(1, ...data.map((d) => d.wins));
  const band = PLOT_W / Math.max(1, data.length);
  const barWidth = Math.min(28, band * 0.68);
  const every = labelEvery(data.length);
  const best = data.reduce((a, b) => (b.wins > a.wins ? b : a), data[0]);

  return (
    <ChartFrame
      title="Wins by season"
      unit="wins per season"
      summary={
        data.length
          ? `Wins per season from ${data[0].season} to ${data[data.length - 1].season}. Peak: ${best.wins} wins in ${best.season}.`
          : "No seasons in range."
      }
      isEmpty={data.length === 0}
      table={<DataTable caption="Wins by season" rows={data} valueHeader="Wins" value={(r) => String(r.wins)} />}
    >
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {ticks(max).map((tick) => {
          const y = PAD.top + PLOT_H - (tick / max) * PLOT_H;
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke={AXIS} strokeWidth="1" />
              <text x={PAD.left - 8} y={y + 4} textAnchor="end" fill={TICK} fontSize="10" fontFamily="var(--mono)">
                {tick}
              </text>
            </g>
          );
        })}
        {data.map((row, index) => {
          const height = (row.wins / max) * PLOT_H;
          const x = PAD.left + index * band + (band - barWidth) / 2;
          return (
            <g key={row.season}>
              <rect
                x={x}
                y={PAD.top + PLOT_H - height}
                width={barWidth}
                height={Math.max(row.wins > 0 ? 2 : 0, height)}
                fill={color}
                rx="2"
              >
                <title>{`${row.season}: ${row.wins} wins from ${row.entries} entries`}</title>
              </rect>
              {index % every === 0 && (
                <text
                  x={x + barWidth / 2}
                  y={H - 12}
                  textAnchor="middle"
                  fill={TICK}
                  fontSize="10"
                  fontFamily="var(--mono)"
                >
                  {String(row.season).slice(2)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + PLOT_H} y2={PAD.top + PLOT_H} stroke={AXIS} />
      </svg>
    </ChartFrame>
  );
}

/**
 * Average classified position over time. A line, because this is a continuous
 * trend across ordered seasons.
 *
 * The y axis is inverted: P1 sits at the top, because "up = better" is what a
 * reader expects and an un-inverted position axis reads backwards.
 */
export function AvgPositionBySeason({ data, color = SERIES[1] }: { data: SeasonStats[]; color?: string }) {
  const points = data.filter((d) => d.avg_classified_position !== null);
  const max = Math.ceil(Math.max(3, ...points.map((d) => d.avg_classified_position!)));
  const band = PLOT_W / Math.max(1, points.length);
  const every = labelEvery(points.length);

  const xy = (row: SeasonStats, index: number) => ({
    x: PAD.left + index * band + band / 2,
    // Inverted: position 1 renders at the top of the plot.
    y: PAD.top + ((row.avg_classified_position! - 1) / (max - 1)) * PLOT_H,
  });

  return (
    <ChartFrame
      title="Average classified position by season"
      unit="mean classification · lower is better"
      summary={
        points.length
          ? `Average classified position per season from ${points[0].season} to ${points[points.length - 1].season}. Best season average: P${dec(Math.min(...points.map((p) => p.avg_classified_position!)))}.`
          : "No seasons in range."
      }
      isEmpty={points.length === 0}
      table={
        <DataTable
          caption="Average classified position by season"
          rows={points}
          valueHeader="Avg classified pos"
          value={(r) => dec(r.avg_classified_position)}
        />
      }
    >
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {ticks(max).filter((t) => t >= 1).map((tick) => {
          const y = PAD.top + ((tick - 1) / (max - 1)) * PLOT_H;
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke={AXIS} strokeWidth="1" />
              <text x={PAD.left - 8} y={y + 4} textAnchor="end" fill={TICK} fontSize="10" fontFamily="var(--mono)">
                P{tick}
              </text>
            </g>
          );
        })}
        <polyline
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeLinejoin="round"
          points={points.map((row, i) => { const p = xy(row, i); return `${p.x},${p.y}`; }).join(" ")}
        />
        {points.map((row, index) => {
          const p = xy(row, index);
          return (
            <g key={row.season}>
              {/* Generous invisible hit area so the tooltip is reachable on touch. */}
              <circle cx={p.x} cy={p.y} r="12" fill="transparent">
                <title>{`${row.season}: average P${dec(row.avg_classified_position)} from ${row.entries} entries`}</title>
              </circle>
              <circle cx={p.x} cy={p.y} r="3" fill={color} />
              {index % every === 0 && (
                <text x={p.x} y={H - 12} textAnchor="middle" fill={TICK} fontSize="10" fontFamily="var(--mono)">
                  {String(row.season).slice(2)}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + PLOT_H} y2={PAD.top + PLOT_H} stroke={AXIS} />
      </svg>
    </ChartFrame>
  );
}
