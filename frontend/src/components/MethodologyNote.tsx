import { useState } from "react";
import type { MetricDoc } from "../types";
import { Badge } from "./ui";

/**
 * Inline methodology for one metric, served from the backend registry.
 *
 * The definition shown here is the same object the API publishes at
 * /api/analytics/metrics, so the explanation beside a number cannot drift
 * from the code that produced it.
 *
 * Collapsed by default: an analyst scanning the page should not have to read
 * a paragraph before seeing the data, but must never be more than one click
 * from knowing how it was derived.
 */
export function MethodologyNote({ metric }: { metric: MetricDoc }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="card"
      style={{ padding: "12px 16px", marginBottom: 16, background: "var(--elevated)" }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <Badge tone="info">Method</Badge>
        <span className="mono" style={{ fontSize: 12, color: "var(--info)" }}>
          {metric.formula}
        </span>
        {metric.min_sample !== null && (
          <span className="mono" style={{ fontSize: 11, color: "var(--text-faint)" }}>
            MIN SAMPLE {metric.min_sample}
          </span>
        )}
        <button
          className="btn"
          style={{ marginLeft: "auto", minHeight: 28, padding: "4px 10px", fontSize: 12 }}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "How is this calculated?"}
        </button>
      </div>

      <p style={{ fontSize: 13, color: "var(--text-dim)", margin: "8px 0 0" }}>{metric.definition}</p>

      {open && (
        <dl style={{ margin: "12px 0 0", display: "grid", gap: 8 }}>
          <div>
            <dt className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)" }}>
              SOURCE COLUMNS
            </dt>
            <dd className="mono" style={{ margin: 0, fontSize: 12 }}>
              {metric.columns.join(" · ")}
            </dd>
          </div>
          <div>
            <dt className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)" }}>
              EDGE CASES
            </dt>
            <dd style={{ margin: 0, fontSize: 13, color: "var(--text-dim)" }}>{metric.edge_cases}</dd>
          </div>
          <div>
            <dt className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--warning)" }}>
              LIMITATIONS
            </dt>
            <dd style={{ margin: 0, fontSize: 13, color: "var(--text-dim)" }}>{metric.limitations}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
