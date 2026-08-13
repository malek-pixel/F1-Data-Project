import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ROUTE } from "../components/CommandPalette";
import { SearchField } from "../components/SearchField";
import { EmptyState } from "../components/States";
import { PageHeader, Panel, PaneHead } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { qs } from "../services/api";
import type { SearchHit } from "../types";

/**
 * Global search as a page (mockup § 13).
 *
 * The ⌘K palette is the same index in a modal: it answers "take me to this
 * one thing". This page answers "show me everything that matches", which is
 * why it is linkable (`/search?q=...`), grouped, and unbounded by the eight
 * rows a modal can show without becoming a scroll trap.
 */

const GROUPS: { kind: SearchHit["kind"]; label: string }[] = [
  { kind: "driver", label: "DRIVERS" },
  { kind: "constructor", label: "CONSTRUCTORS" },
  { kind: "circuit", label: "CIRCUITS" },
  { kind: "race", label: "RACES" },
  { kind: "season", label: "SEASONS" },
];

/** Navigable destinations, matched client-side: the API indexes data, not routes. */
const PAGES: { to: string; label: string; sub: string; terms: string }[] = [
  { to: "/", label: "Overview", sub: "Latest season standings and entry points", terms: "overview home standings" },
  { to: "/drivers", label: "Driver library", sub: "Every driver in the dataset", terms: "drivers library people" },
  { to: "/constructors", label: "Team library", sub: "Every constructor in the dataset", terms: "constructors teams library" },
  { to: "/circuits", label: "Circuit library", sub: "Tracks and track maps", terms: "circuits tracks maps venues" },
  { to: "/races", label: "Race explorer", sub: "Every race, season by season", terms: "races grands prix results" },
  { to: "/seasons", label: "Seasons", sub: "Season standings and progression", terms: "seasons years championship" },
  { to: "/cars", label: "Car library", sub: "Chassis by team and season", terms: "cars chassis machinery" },
  { to: "/compare", label: "Compare", sub: "Head-to-head between two drivers", terms: "compare head to head versus" },
  { to: "/records", label: "Records", sub: "Extremes and leaderboards", terms: "records leaders best most" },
  { to: "/dataset", label: "Dataset", sub: "Schema, coverage and known issues", terms: "dataset data schema coverage" },
];

function Row({ to, label, sub }: { to: string; label: string; sub: string }) {
  return (
    <Link to={to} className="search-row">
      <span className="search-row__label">{label}</span>
      <span className="search-row__sub mono">{sub}</span>
    </Link>
  );
}

export function Search() {
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(urlQuery);

  // Arriving from the palette (or a shared link) must fill the input.
  useEffect(() => setQuery(urlQuery), [urlQuery]);

  const debounced = useDebounced(query, 220);
  const text = debounced.trim();

  // The URL is the query: a search result set is a shareable state.
  useEffect(() => {
    const next = new URLSearchParams(params);
    if (text) next.set("q", text);
    else next.delete("q");
    if (next.toString() !== params.toString()) setParams(next, { replace: true });
    // `params` is intentionally not a dependency: it is what we are writing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const { data, loading } = useApi<{ results: SearchHit[] }>(text ? `/search${qs({ q: text, limit: 25 })}` : null);
  const results = data?.results ?? [];
  const pages = text
    ? PAGES.filter((p) => `${p.label} ${p.terms}`.toLowerCase().includes(text.toLowerCase()))
    : [];
  const total = results.length + pages.length;

  return (
    <>
      <PageHeader
        eyebrow="GLOBAL SEARCH"
        title="Search"
        sub="Drivers, constructors, circuits, races, seasons and pages. ⌘K opens the same index in a modal."
      />

      <div className="controls">
        <SearchField
          id="search-q"
          label="QUERY"
          className="searchfield--grow"
          autoFocus
          placeholder="e.g. alonso · 2004 monza · spa · ferrari"
          value={query}
          loading={loading}
          onChange={setQuery}
        />
      </div>

      {!text ? (
        <EmptyState
          title="Search across the dataset"
          body="Type a driver, constructor, circuit, race or season. Try “alonso”, “2004 monza” or “spanish grand prix”."
        />
      ) : loading ? (
        <p style={{ fontSize: 13, color: "var(--text-dim)" }}>Searching…</p>
      ) : total === 0 ? (
        <EmptyState
          title={`No matches for “${text}”`}
          body="Coverage starts in 2000 — records before that season are outside this dataset's scope."
        />
      ) : (
        <>
          <p className="mono" style={{ fontSize: 12, color: "var(--text-faint)" }}>
            {total} {total === 1 ? "MATCH" : "MATCHES"} · QUERY “{text.toUpperCase()}”
          </p>
          {GROUPS.map(({ kind, label }) => {
            const hits = results.filter((hit) => hit.kind === kind);
            if (hits.length === 0) return null;
            return (
              <Panel key={kind}>
                <PaneHead title={label} meta={`${hits.length} ${hits.length === 1 ? "result" : "results"}`} />
                <div className="search-group">
                  {hits.map((hit) => (
                    <Row
                      key={`${hit.kind}-${hit.id}`}
                      to={ROUTE[hit.kind](hit.id)}
                      label={hit.label}
                      sub={hit.sublabel}
                    />
                  ))}
                </div>
              </Panel>
            );
          })}
          {pages.length > 0 && (
            <Panel>
              <PaneHead title="PAGES" meta={`${pages.length} ${pages.length === 1 ? "result" : "results"}`} />
              <div className="search-group">
                {pages.map((page) => (
                  <Row key={page.to} to={page.to} label={page.label} sub={page.sub} />
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </>
  );
}
