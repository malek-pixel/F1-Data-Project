import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi, useDebounced } from "../hooks/useApi";
import { qs } from "../services/api";
import type { SearchHit } from "../types";

const ROUTE: Record<SearchHit["kind"], (id: number) => string> = {
  driver: (id) => `/drivers/${id}`,
  constructor: (id) => `/constructors/${id}`,
  circuit: (id) => `/circuits/${id}`,
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
  const results = data?.results ?? [];

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
          aria-controls="palette-results"
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
              setActive((i) => Math.min(i + 1, results.length - 1));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            }
            if (event.key === "Enter" && results[active]) go(results[active]);
          }}
        />
        <ul className="palette__results" id="palette-results" role="listbox" aria-label="Search results">
          {loading && <li style={{ padding: 16, fontSize: 13, color: "var(--text-dim)" }}>Searching…</li>}
          {!loading && debounced.trim() && results.length === 0 && (
            <li style={{ padding: 16, fontSize: 13, color: "var(--text-dim)" }}>
              No matches for “{debounced}”.
            </li>
          )}
          {results.map((hit, index) => (
            <li key={`${hit.kind}-${hit.id}`} role="option" aria-selected={index === active}>
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
