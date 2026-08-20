import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";

import { Stagger, staggerItem } from "../components/motion";
import { SearchField } from "../components/SearchField";
import { driverPhoto } from "../components/driverPhoto";
import { teamLogo } from "../components/teamLogo";
import { Async } from "../components/States";
import { dec, num, pct } from "../components/format";
import { Badge, FilterChip, PageHeader, Pagination, Panel, PaneHead } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import { qs } from "../services/api";
import type { NamedStats, Page } from "../types";

/** Grid item and link in one element: an extra wrapper would become the grid
 *  item and the card would lose the borders that draw the gallery's rules. */
const MotionLink = motion.create(Link);

const PAGE_SIZE = 25;

/**
 * Shared driver / constructor library.
 *
 * All filtering, sorting and paging is server-side -- the browser never holds
 * the full dataset to sort it locally.
 */
export function EntityLibrary({
  kind,
  title,
  eyebrow,
}: {
  kind: "drivers" | "constructors";
  title: string;
  eyebrow: string;
}) {
  // Filters live in the URL: a filtered view is a linkable analytical state,
  // and it survives refresh and back-navigation.
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") ?? "wins";
  const minEntries = Number(params.get("min") ?? 1);
  const offset = Number(params.get("offset") ?? 0);
  const urlSearch = params.get("q") ?? "";

  // The text input stays local so typing is not throttled by history writes;
  // the debounced value is what reaches the URL and the API.
  const [search, setSearch] = useState(urlSearch);

  const coverage = useCoverage();
  const debounced = useDebounced(search);
  const logo = (name: string) => (kind === "constructors" ? teamLogo(name) : null);
  const portrait = (name: string) => (kind === "drivers" ? driverPhoto(name) : null);

  const write = (next: Record<string, string | number | null>) => {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value === null || value === "" || value === undefined) updated.delete(key);
      else updated.set(key, String(value));
    }
    setParams(updated, { replace: true });
  };
  const state = useApi<Page<NamedStats>>(
    `/${kind}${qs({ search: debounced, sort, min_entries: minEntries, limit: PAGE_SIZE, offset })}`,
  );

  // Any filter change invalidates the current page number.
  const setSort = (value: string) => write({ sort: value, offset: null });
  const setMinEntries = (value: number) => write({ min: value === 1 ? null : value, offset: null });
  const setOffset = (value: number) => write({ offset: value === 0 ? null : value });
  const onSearch = (value: string) => {
    setSearch(value);
    write({ q: value || null, offset: null });
  };

  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        sub={`Seasons ${coverage}. Rates use race entries as the denominator; entries include retirements.`}
      />

      <div className="controls">
        <SearchField
          id="lib-search"
          label="SEARCH"
          className="searchfield--wide"
          placeholder={kind === "drivers" ? "Driver name…" : "Constructor name…"}
          value={search}
          loading={state.loading}
          onChange={onSearch}
        />
        <div className="field">
          <label htmlFor="lib-sort">SORT BY</label>
          <select id="lib-sort" className="select" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="wins">Wins</option>
            <option value="podiums">Podiums</option>
            <option value="entries">Entries</option>
            <option value="win_rate">Win rate</option>
            <option value="podium_rate">Podium rate</option>
            <option value="avg_position">Avg classified position</option>
            <option value="name">Name (A–Z)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="lib-min">MIN ENTRIES</label>
          <select
            id="lib-min"
            className="select"
            value={minEntries}
            onChange={(event) => setMinEntries(Number(event.target.value))}
          >
            <option value={1}>Any</option>
            <option value={10}>10+</option>
            <option value={50}>50+</option>
            <option value={100}>100+</option>
          </select>
        </div>
      </div>

      {minEntries === 1 && (sort === "win_rate" || sort === "podium_rate" || sort === "avg_position") && (
        <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 0 }}>
          <Badge tone="warning">Small samples included</Badge>{" "}
          Rate and average columns are volatile below 10 entries. Raise the minimum to compare like with like.
        </p>
      )}

      <Async state={state} loadingRows={8}>
        {(page) => (
          <>
            <Panel>
              <PaneHead
                title={`${title} · ${page.total.toLocaleString()} rows`}
                meta={`SCOPE ${coverage} · SORTED BY ${sort.replace("_", " ").toUpperCase()}`}
              />
              {(debounced || minEntries > 1) && (
                <div className="filter-row">
                  <span className="mono filter-row__label">ACTIVE</span>
                  {debounced && <FilterChip label={`name: ${debounced}`} onClear={() => onSearch("")} />}
                  {minEntries > 1 && (
                    <FilterChip label={`min entries: ${minEntries}`} onClear={() => setMinEntries(1)} />
                  )}
                  <button
                    className="chip__clear mono"
                    onClick={() => {
                      onSearch("");
                      setMinEntries(1);
                    }}
                  >
                    Clear all
                  </button>
                </div>
              )}
              {/* Cards, not a table. The mockup's library sections (06/07) are
                  the primary shape for browsing entities; every column the
                  explorer table carried is kept on the card, so nothing is
                  lost by dropping the table. */}
                <Stagger className="gallery">
                  {page.items.map((row, i) => (
                    <MotionLink
                      key={row.id}
                      variants={staggerItem}
                      to={`/${kind}/${row.id}`}
                      className="gallery__card"
                    >
                      {/* Every driver has a portrait and every browsable
                          constructor a logo. The labelled frame is the fallback
                          for an entity a later ETL run adds before its artwork
                          exists -- never a generic badge, which would imply an
                          identity we do not have. */}
                      {logo(row.name) ? (
                        <div className="gallery__media gallery__media--logo">
                          <img src={logo(row.name)!} alt="" loading="lazy" decoding="async" width={320} height={320} />
                        </div>
                      ) : portrait(row.name) ? (
                        <div className="gallery__media gallery__media--portrait">
                          <img src={portrait(row.name)!} alt="" loading="lazy" decoding="async" width={340} height={340} />
                        </div>
                      ) : (
                        <div className="gallery__media mono">
                          {kind === "drivers" ? "PORTRAIT" : "LIVERY"}
                          <span>to be added</span>
                        </div>
                      )}
                      <div className="gallery__rank mono">
                        {String(page.offset + i + 1).padStart(2, "0")}
                      </div>
                      <div className="gallery__name">{row.name}</div>
                      <div className="gallery__stats mono">
                        <span>
                          W <strong>{num(row.wins)}</strong>
                        </span>
                        <span>
                          P <strong>{num(row.podiums)}</strong>
                        </span>
                        <span>
                          S <strong>{num(row.entries)}</strong>
                        </span>
                      </div>
                      <div className="gallery__stats mono" style={{ marginTop: 4 }}>
                        <span
                          style={row.rates_reliable ? undefined : { color: "var(--warning)" }}
                          title={row.rates_reliable ? undefined : `Small sample: ${row.entries} entries`}
                        >
                          WIN% <strong>{pct(row.win_rate)}</strong>
                          {!row.rates_reliable && <span aria-label=" (small sample)"> *</span>}
                        </span>
                        <span>
                          AVG P <strong>{dec(row.avg_classified_position)}</strong>
                        </span>
                      </div>
                      {/* The mockup's cards carry nationality and a title
                          count. Nationality is real and now carried on the
                          listing -- this slot used to read "NAT —" under a
                          tooltip saying it was not in the source, for a column
                          every driver and constructor has. Titles are
                          derivable from the standings but not computed yet,
                          which is a different statement from unavailable. */}
                      <div className="gallery__stats mono" style={{ marginTop: 4 }}>
                        {row.nationality ? (
                          <span>
                            NAT <strong>{row.nationality}</strong>
                          </span>
                        ) : (
                          <span className="pending" title="No nationality recorded for this entity">
                            NAT —
                          </span>
                        )}
                        <span
                          className="pending"
                          title="Points and standings exist; counting title-winning seasons is not built yet"
                        >
                          WDC —
                        </span>
                      </div>
                    </MotionLink>
                  ))}
                  {page.items.length === 0 && (
                    <p className="table-empty">
                      {debounced
                        ? `No ${kind} match “${debounced}” with these filters.`
                        : `No ${kind} match these filters.`}
                    </p>
                  )}
                </Stagger>
            </Panel>
            <Pagination total={page.total} limit={page.limit} offset={page.offset} onChange={setOffset} />
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              * fewer than 10 entries — rate shown but not comparable. Fields marked “—” need source
              columns the dataset does not have yet.
            </p>
          </>
        )}
      </Async>
    </>
  );
}
