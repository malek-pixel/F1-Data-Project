import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ComparisonBar } from "../charts/ContributionChart";
import { Async, EmptyState } from "../components/States";
import { dec, num, pct, seasonSpan } from "../components/format";
import { Badge, PageHeader, Panel, PaneHead, PendingValue, SectionTitle, Tabs } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import { qs } from "../services/api";
import type { Comparison, NamedStats, Page, Stats } from "../types";

type Kind = "drivers" | "constructors";

/** Typeahead entity picker backed by the same server-side search the library uses. */
function EntityPicker({
  kind,
  label,
  value,
  onChange,
}: {
  kind: Kind;
  label: string;
  value: NamedStats | null;
  onChange: (entity: NamedStats | null) => void;
}) {
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query);
  const state = useApi<Page<NamedStats>>(
    debounced.trim() ? `/${kind}${qs({ search: debounced.trim(), limit: 6, sort: "wins" })}` : null,
  );

  if (value) {
    return (
      <div className="card" style={{ padding: 16 }}>
        <div className="card__label mono">{label}</div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <strong style={{ fontSize: 18 }}>{value.name}</strong>
          <button className="btn" onClick={() => onChange(null)}>
            Change
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="card__label mono">{label}</div>
      <div className="field">
        <label htmlFor={`pick-${label}`} style={{ position: "absolute", left: -9999 }}>
          {label}
        </label>
        <input
          id={`pick-${label}`}
          className="input"
          type="search"
          placeholder={kind === "drivers" ? "Search driver…" : "Search constructor…"}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      {state.data && (
        <ul style={{ listStyle: "none", margin: "8px 0 0", padding: 0 }}>
          {state.data.items.length === 0 && (
            <li style={{ fontSize: 13, color: "var(--text-dim)", padding: "8px 0" }}>
              No matches for “{debounced}”.
            </li>
          )}
          {state.data.items.map((item) => (
            <li key={item.id}>
              <button
                className="palette__item"
                style={{ padding: "8px 0" }}
                onClick={() => {
                  onChange(item);
                  setQuery("");
                }}
              >
                <span>{item.name}</span>
                <span className="palette__sub">{item.wins} wins</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Raw totals and per-start rates, deliberately separated.
 *
 * A driver with 250 starts accumulates more wins than one with 50 purely from
 * opportunity. Showing totals alone rewards longevity; showing rates alone
 * rewards short careers in strong cars. Both are shown, labelled, and neither
 * is combined into a single score.
 */
function StatsColumns({ left, right, title }: { left: Stats; right: Stats; title: string }) {
  return (
    <Panel>
      <PaneHead title={title} meta="LEFT vs RIGHT" />
      <div className="panel--pad">

      <div className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)", margin: "4px 0 10px" }}>
        RAW TOTALS · SENSITIVE TO CAREER LENGTH
      </div>
      <ComparisonBar label="STARTS" leftLabel="left" rightLabel="right" left={left.entries} right={right.entries} format={num} />
      <ComparisonBar label="WINS" leftLabel="left" rightLabel="right" left={left.wins} right={right.wins} format={num} />
      <ComparisonBar label="PODIUMS" leftLabel="left" rightLabel="right" left={left.podiums} right={right.podiums} format={num} />
      <ComparisonBar label="TOP 10s" leftLabel="left" rightLabel="right" left={left.top10} right={right.top10} format={num} />

      <div className="mono" style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-faint)", margin: "16px 0 10px", paddingTop: 12, borderTop: "1px solid var(--border)" }}>
        PER START · NORMALISED FOR CAREER LENGTH
      </div>
      <ComparisonBar label="WIN RATE" leftLabel="left" rightLabel="right" left={left.win_rate} right={right.win_rate} format={(v) => pct(v)} />
      <ComparisonBar
        label="PODIUM RATE"
        leftLabel="left"
        rightLabel="right"
        left={left.podium_rate}
        right={right.podium_rate}
        format={(v) => pct(v)}
      />
      <ComparisonBar
        label="TOP-10 RATE"
        leftLabel="left"
        rightLabel="right"
        left={left.top10_rate}
        right={right.top10_rate}
        format={(v) => pct(v)}
      />
      <ComparisonBar
        label="AVG CLASSIFIED POS"
        leftLabel="left"
        rightLabel="right"
        left={left.avg_classified_position}
        right={right.avg_classified_position}
        format={(v) => dec(v)}
        lowerIsBetter
      />
      <ComparisonBar
        label="BEST CLASSIFIED POS"
        leftLabel="left"
        rightLabel="right"
        left={left.best_classified_position}
        right={right.best_classified_position}
        format={(v) => (v === null ? "—" : `P${v}`)}
        lowerIsBetter
      />

      {/* The mockup compares poles, points, points-per-start, DNFs and titles
          as well. None has a source column, so each keeps its row and says so
          rather than vanishing from the comparison. */}
      <div
        className="mono"
        style={{
          fontSize: 10,
          letterSpacing: "0.08em",
          color: "var(--text-faint)",
          margin: "16px 0 10px",
          paddingTop: 12,
          borderTop: "1px solid var(--border)",
        }}
      >
        NOT COMPARABLE — NO SOURCE COLUMN
      </div>
      <ul className="pending-rows mono">
        {[
          ["POLES", "no qualifying data"],
          ["POINTS", "no points column"],
          ["POINTS / START", "no points column"],
          ["FINISH RATE", "no finishing-status column"],
          ["DNFs", "no finishing-status column"],
          ["TITLES", "titles require points"],
        ].map(([label, why]) => (
          <li key={label}>
            <PendingValue title={why} />
            <span className="pending-rows__label">{label}</span>
            <PendingValue title={why} />
          </li>
        ))}
      </ul>
      </div>
    </Panel>
  );
}

export function Compare() {
  const coverage = useCoverage();

  // Comparison state lives in the URL so a view can be bookmarked, shared and
  // survive a refresh. The picked entities are resolved from their ids rather
  // than held only in memory.
  const [params, setParams] = useSearchParams();
  const kind: Kind = params.get("kind") === "constructors" ? "constructors" : "drivers";
  const leftId = params.get("left");
  const rightId = params.get("right");

  const [left, setLeft] = useState<NamedStats | null>(null);
  const [right, setRight] = useState<NamedStats | null>(null);

  // Rehydrate from the URL on load or when the link changes underneath us.
  const leftLookup = useApi<{ id: number; name: string }>(
    leftId && left?.id !== Number(leftId) ? `/${kind}/${leftId}` : null,
  );
  const rightLookup = useApi<{ id: number; name: string }>(
    rightId && right?.id !== Number(rightId) ? `/${kind}/${rightId}` : null,
  );
  useEffect(() => {
    if (leftLookup.data) setLeft({ id: leftLookup.data.id, name: leftLookup.data.name } as NamedStats);
  }, [leftLookup.data]);
  useEffect(() => {
    if (rightLookup.data) setRight({ id: rightLookup.data.id, name: rightLookup.data.name } as NamedStats);
  }, [rightLookup.data]);
  useEffect(() => {
    if (!leftId) setLeft(null);
    if (!rightId) setRight(null);
  }, [leftId, rightId]);

  const write = (next: { kind?: Kind; left?: number | null; right?: number | null }) => {
    const updated = new URLSearchParams(params);
    if (next.kind) updated.set("kind", next.kind);
    for (const side of ["left", "right"] as const) {
      if (side in next) {
        const value = next[side];
        if (value === null || value === undefined) updated.delete(side);
        else updated.set(side, String(value));
      }
    }
    setParams(updated, { replace: true });
  };

  const chooseLeft = (entity: NamedStats | null) => {
    setLeft(entity);
    write({ left: entity?.id ?? null });
  };
  const chooseRight = (entity: NamedStats | null) => {
    setRight(entity);
    write({ right: entity?.id ?? null });
  };

  const ready = left && right && left.id !== right.id;
  const state = useApi<Comparison>(ready ? `/compare/${kind}${qs({ left: left!.id, right: right!.id })}` : null);

  const switchKind = (next: Kind) => {
    setLeft(null);
    setRight(null);
    write({ kind: next, left: null, right: null });
  };

  return (
    <>
      <PageHeader
        eyebrow="COMPARE"
        title="Head-to-head"
        sub="Compare two drivers or two constructors on the metrics the dataset supports."
      />

      <Tabs
        label="Comparison type"
        active={kind}
        onChange={switchKind}
        tabs={[
          { id: "drivers", label: "Driver vs driver" },
          { id: "constructors", label: "Constructor vs constructor" },
        ]}
      />

      <div className="grid grid--2">
        <EntityPicker kind={kind} label="LEFT" value={left} onChange={chooseLeft} />
        <EntityPicker kind={kind} label="RIGHT" value={right} onChange={chooseRight} />
      </div>

      {left && right && left.id === right.id && (
        <p style={{ color: "var(--warning)", fontSize: 13 }}>Pick two different entities to compare.</p>
      )}

      {!ready ? (
        <div style={{ marginTop: 24 }}>
          <EmptyState
            title="Choose two to compare"
            body="Search and select an entity on each side. Only metrics the source data supports are compared — no placeholders for missing statistics."
          />
        </div>
      ) : (
        <Async state={state} loadingRows={6}>
          {(comparison) => (
            <>
              <SectionTitle aside={`${comparison.left_name} vs ${comparison.right_name}`}>Career totals</SectionTitle>

              {/* The caveat sits above the numbers, not in a footnote below them. */}
              <Panel pad>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 8 }}>
                  <Badge tone={comparison.comparable ? "info" : "warning"}>
                    {comparison.comparable ? "Comparable sample" : "Read with caution"}
                  </Badge>
                  <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
                    {comparison.shared_seasons.length > 0
                      ? `Overlapping seasons: ${seasonSpan(comparison.shared_seasons)} (${comparison.shared_seasons.length})`
                      : "No overlapping seasons — career totals compare different eras."}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--text-dim)", margin: 0 }}>{comparison.methodology}</p>
              </Panel>

              <div className="chart__legend" style={{ marginBottom: 12 }}>
                <span>
                  <span className="chart__swatch" style={{ background: "var(--accent)" }} />
                  {comparison.left_name}
                </span>
                <span>
                  <span className="chart__swatch" style={{ background: "var(--info)" }} />
                  {comparison.right_name}
                </span>
              </div>

              <div className="grid grid--2">
                <StatsColumns left={comparison.left} right={comparison.right} title={`FULL CAREER · ${coverage}`} />
                {comparison.left_shared && comparison.right_shared ? (
                  <StatsColumns
                    left={comparison.left_shared}
                    right={comparison.right_shared}
                    title={`SHARED SEASONS ONLY · ${seasonSpan(comparison.shared_seasons)}`}
                  />
                ) : (
                  <EmptyState
                    title="No shared seasons"
                    body="These two were never active in the same season, so there is no like-for-like window to compare. Career totals reflect different eras, machinery and calendar lengths."
                  />
                )}
              </div>

              <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 16, maxWidth: "80ch" }}>
                No overall score is produced. A single number would have to weight career length, car
                competitiveness, teammate strength and era against each other, and no defensible weighting exists
                — so the components are shown separately instead. Qualifying, points and reliability, which would
                round out this comparison, are absent from the dataset.
              </p>
            </>
          )}
        </Async>
      )}
    </>
  );
}
