import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DataTable } from "../components/DataTable";
import { Async } from "../components/States";
import { dec, num, pct } from "../components/format";
import { Badge, FilterChip, PageHeader, Pagination, Panel, PaneHead, PendingValue, Segmented } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import { qs } from "../services/api";
import type { NamedStats, Page } from "../types";

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
  // The mockup has both an explorer table (section 03/04) and a library
  // gallery (section 06/07) over the same entities. One toggle, not two
  // routes: the data and every filter are identical, only the shape differs.
  const [view, setView] = useState<"table" | "gallery">("table");

  const coverage = useCoverage();
  const debounced = useDebounced(search);

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
        <div className="field">
          <label htmlFor="lib-search">SEARCH</label>
          <input
            id="lib-search"
            className="input"
            type="search"
            placeholder={kind === "drivers" ? "Driver name…" : "Constructor name…"}
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            style={{ minWidth: 220 }}
          />
        </div>
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
        <div className="field">
          <label htmlFor="lib-view">VIEW</label>
          <Segmented
            label={`${title} view`}
            active={view}
            onChange={setView}
            options={[
              { id: "table", label: "Table" },
              { id: "gallery", label: "Gallery" },
            ]}
          />
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
              {view === "gallery" ? (
                <div className="gallery">
                  {page.items.map((row, i) => (
                    <Link key={row.id} to={`/${kind}/${row.id}`} className="gallery__card">
                      {/* The mockup shows a driver portrait / team livery here.
                          No image set ships with this dataset, so the frame
                          stays and states that rather than showing a stock
                          photo or an invented livery. */}
                      <div className="gallery__media mono">
                        {kind === "drivers" ? "PORTRAIT" : "LIVERY"}
                        <span>to be added</span>
                      </div>
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
                        <span className="pending" title="Titles require a points column">
                          WDC —
                        </span>
                      </div>
                    </Link>
                  ))}
                  {page.items.length === 0 && (
                    <p className="table-empty">No {kind} match these filters.</p>
                  )}
                </div>
              ) : (
              <DataTable
                caption={`${title} ranked by ${sort}`}
                rows={page.items}
                rowKey={(row) => row.id}
                sort={sort}
                onSort={setSort}
                emptyMessage={
                  debounced
                    ? `No ${kind} match “${debounced}” with these filters.`
                    : `No ${kind} match these filters.`
                }
                columns={[
                  {
                    key: "rank",
                    header: "#",
                    numeric: true,
                    render: (_r, i) => <span className="mono rank">{String(page.offset + i + 1).padStart(2, "0")}</span>,
                  },
                  {
                    key: "name",
                    header: kind === "drivers" ? "Driver" : "Constructor",
                    sortKey: "name",
                    render: (row) => (
                      <Link to={`/${kind}/${row.id}`} style={{ fontWeight: 500 }}>
                        {row.name}
                      </Link>
                    ),
                  },
                  /* The mockup carries nationality (drivers) and base (teams).
                     Neither is in the seven source columns, so the column stays
                     and says so rather than disappearing from the design. */
                  {
                    key: "meta",
                    header: kind === "drivers" ? "Nat" : "Base",
                    render: () => (
                      <PendingValue
                        title={
                          kind === "drivers"
                            ? "Nationality is not in results.csv -- Ergast drivers.csv would supply it"
                            : "Team base is not in results.csv -- Ergast constructors.csv would supply it"
                        }
                      />
                    ),
                  },
                  { key: "entries", header: "Starts", numeric: true, sortKey: "entries", render: (r) => num(r.entries) },
                  { key: "wins", header: "Wins", numeric: true, sortKey: "wins", render: (r) => num(r.wins) },
                  { key: "podiums", header: "Pods", numeric: true, sortKey: "podiums", render: (r) => num(r.podiums) },
                  {
                    key: "win_rate",
                    header: "Win rate",
                    numeric: true,
                    sortKey: "win_rate",
                    render: (r) => (
                      <span
                        style={r.rates_reliable ? undefined : { color: "var(--warning)" }}
                        title={r.rates_reliable ? undefined : `Small sample: ${r.entries} entries`}
                      >
                        {pct(r.win_rate)}
                        {!r.rates_reliable && <span aria-label=" (small sample)"> *</span>}
                      </span>
                    ),
                  },
                  {
                    key: "avg",
                    header: "Avg P",
                    numeric: true,
                    sortKey: "avg_position",
                    render: (r) => dec(r.avg_classified_position),
                  },
                  {
                    key: "titles",
                    header: kind === "drivers" ? "Titles" : "Titles",
                    numeric: true,
                    render: () => <PendingValue title="Championship titles need a points column; results.csv has none" />,
                  },
                ]}
              />
              )}
            </Panel>
            <Pagination total={page.total} limit={page.limit} offset={page.offset} onChange={setOffset} />
            <p style={{ fontSize: 12, color: "var(--text-faint)" }}>
              * fewer than 10 entries — rate shown but not comparable. Columns marked “— to be
              added” need source columns the dataset does not have yet.
            </p>
          </>
        )}
      </Async>
    </>
  );
}
