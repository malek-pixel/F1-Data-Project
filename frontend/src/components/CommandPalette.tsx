import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi, useDebounced } from "../hooks/useApi";
import { qs } from "../services/api";
import type { SearchHit } from "../types";

export const ROUTE: Record<SearchHit["kind"], (id: number) => string> = {
  driver: (id) => `/drivers/${id}`,
  constructor: (id) => `/constructors/${id}`,
  circuit: (id) => `/circuits/${id}`,
  race: (id) => `/races/${id}`,
  season: (id) => `/seasons/${id}`,
};

/**
 * Global search, opened with ⌘K / Ctrl+K.
 *
 * Fully keyboard-driven: arrows move, Enter opens, Escape closes and returns
 * focus to whatever opened it. Queries are debounced so typing does not fire
 * a request per keystroke, and results come from the API -- nothing here is
 * faked to look responsive.
 */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const openerRef = useRef<Element | null>(null);
  const navigate = useNavigate();

  const debounced = useDebounced(query, 220);
  const { data, loading } = useApi<{ results: SearchHit[] }>(
    debounced.trim() ? `/search${qs({ q: debounced.trim(), limit: 8 })}` : null,
  );
  // The modal stays a jump-to-thing, not a results browser: it shows the top
  // handful and hands the rest to the full search page (mockup § 13).
  const results = (data?.results ?? []).slice(0, 8);
  const query_ = debounced.trim();
  // The "see all" row is the last item in the same arrow-key list, so Enter on
  // it behaves like Enter on any other row.
  const rowCount = results.length + (query_ ? 1 : 0);

  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement;
      inputRef.current?.focus();
    } else {
      setQuery("");
      setActive(0);
      (openerRef.current as HTMLElement | null)?.focus?.();
    }
  }, [open]);

  useEffect(() => setActive(0), [debounced]);

  if (!open) return null;

  const go = (hit: SearchHit) => {
    navigate(ROUTE[hit.kind](hit.id));
    onClose();
  };
  const goAll = () => {
    navigate(`/search${qs({ q: query_ })}`);
    onClose();
  };

  return (
    <div
      className="palette__scrim"
      onClick={(event) => event.target === event.currentTarget && onClose()}
      role="presentation"
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search">
        <input
          ref={inputRef}
          className="mono"
          value={query}
          placeholder="Search drivers, teams, circuits, seasons…"
          aria-label="Search query"
          role="combobox"
          aria-expanded="true"
          aria-controls="palette-results"
          // Without this the listbox has a visually highlighted row that no
          // screen reader ever announces: arrow keys move a `data-active`
          // flag while focus never leaves the input.
          aria-activedescendant={
            results[active] ? `palette-opt-${results[active].kind}-${results[active].id}`
              : query_ && active === results.length ? "palette-opt-all" : undefined
          }
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") onClose();
            // aria-modal="true" tells assistive tech the rest of the page is
            // inert, so Tab must not reach it. The dialog's only focusable is
            // this input (results are driven by arrow keys), so both Tab
            // directions stay put.
            if (event.key === "Tab") event.preventDefault();
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((i) => Math.min(i + 1, rowCount - 1));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            }
            if (event.key === "Enter") {
              if (results[active]) go(results[active]);
              else if (query_) goAll();
            }
          }}
        />
        <ul className="palette__results" id="palette-results" role="listbox" aria-label="Search results">
          {loading && <li style={{ padding: 16, fontSize: 13, color: "var(--text-dim)" }}>Searching…</li>}
          {!loading && !query_ && (
            <li style={{ padding: 16, fontSize: 13, color: "var(--text-dim)" }}>
              Search drivers, constructors, circuits, races and seasons.{" "}
              <span className="mono" style={{ color: "var(--text-faint)" }}>
                Try “alonso”, “2004 monza”, “spa”.
              </span>
            </li>
          )}
          {!loading && query_ && results.length === 0 && (
            <li style={{ padding: 16, fontSize: 13, color: "var(--text-dim)" }}>
              No matches for “{debounced}”. Coverage starts in 2000 — earlier records are outside this dataset.
            </li>
          )}
          {results.map((hit, index) => (
            <li key={`${hit.kind}-${hit.id}`} id={`palette-opt-${hit.kind}-${hit.id}`} role="option" aria-selected={index === active}>
              <button
                className="palette__item"
                data-active={index === active}
                onMouseEnter={() => setActive(index)}
                onClick={() => go(hit)}
              >
                <span className="palette__kind">{hit.kind.toUpperCase()}</span>
                <span>{hit.label}</span>
                <span className="palette__sub">{hit.sublabel}</span>
              </button>
            </li>
          ))}
          {query_ && (
            <li id="palette-opt-all" role="option" aria-selected={active === results.length}>
              <button
                className="palette__item"
                data-active={active === results.length}
                onMouseEnter={() => setActive(results.length)}
                onClick={goAll}
              >
                <span className="palette__kind">ALL</span>
                <span>See all results for “{query_}”</span>
                <span className="palette__sub mono">↵</span>
              </button>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

/** Registers the ⌘K / Ctrl+K shortcut. */
export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return { open, setOpen };
}
