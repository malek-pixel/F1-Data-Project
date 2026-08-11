import { NavLink, Outlet, useLocation } from "react-router-dom";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { Icons, type IconName } from "./icons";
import { useApi } from "../hooks/useApi";
import type { Health } from "../types";

/**
 * Application chrome, built to the mockup's three-part frame
 * (`design/F1 Dashboard.dc.html` § Home):
 *
 *   56px icon rail │ provenance bar   (near-black, dataset identity)
 *                  │ context bar      (breadcrumb, search, state)
 *                  │ page content
 *
 * Two deliberate departures, both because the mockup prototyped against
 * sample data and this app runs on the real dataset:
 *
 *   - The rail's trailing settings cog is replaced by Dataset and Methodology.
 *     There is nothing to configure, and a control that does nothing is worse
 *     than one that goes somewhere real.
 *   - The provenance bar shows counts from /health, never literals. The
 *     mockup's "10,551 records · 543 drivers · 24 constructors" were
 *     placeholders; the dataset holds 10,550 · 129 · 38.
 */
interface RailItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  badge?: string;
}

const RAIL: RailItem[] = [
  { to: "/", label: "Overview", icon: "overview", end: true },
  { to: "/drivers", label: "Drivers", icon: "drivers" },
  { to: "/constructors", label: "Constructors", icon: "constructors" },
  { to: "/circuits", label: "Circuits", icon: "circuits" },
  { to: "/races", label: "Races", icon: "races" },
  { to: "/seasons", label: "Seasons", icon: "seasons" },
  { to: "/insights", label: "Insights", icon: "insights" },
  { to: "/records", label: "Records", icon: "records" },
  { to: "/cars", label: "Cars", icon: "cars", badge: "NEW" },
  { to: "/compare", label: "Compare", icon: "compare" },
];

const RAIL_FOOT: RailItem[] = [
  { to: "/dataset", label: "Dataset", icon: "dataset" },
  { to: "/methodology", label: "Methodology", icon: "methodology" },
];

/** Breadcrumb label for the current route, matched longest-prefix-first. */
const CRUMBS: [string, string][] = [
  ["/drivers", "Drivers"],
  ["/constructors", "Constructors"],
  ["/circuits", "Circuits"],
  ["/races", "Races"],
  ["/seasons", "Seasons"],
  ["/compare", "Compare"],
  ["/insights", "Insights"],
  ["/records", "Records"],
  ["/cars", "Cars"],
  ["/dataset", "Dataset"],
  ["/methodology", "Methodology"],
];

function RailLink({ item }: { item: RailItem }) {
  const Icon = Icons[item.icon];
  return (
    <NavLink to={item.to} end={item.end} className="rail__item" title={item.label} aria-label={item.label}>
      <Icon />
      {item.badge && <span className="rail__badge mono">{item.badge}</span>}
    </NavLink>
  );
}

export function Shell() {
  const palette = useCommandPalette();
  const health = useApi<Health>("/health");
  const { pathname } = useLocation();
  const crumb = CRUMBS.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "Overview";
  const info = health.data;

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <div className="shell">
        <div className="rail">
          <div className="rail__brand">
            <img src="/f1-logo.png" alt="F1" />
          </div>
          <nav aria-label="Primary" className="rail__nav">
            {RAIL.map((item) => (
              <RailLink key={item.to} item={item} />
            ))}
          </nav>
          <div className="rail__spacer" />
          <nav aria-label="Reference" className="rail__nav">
            {RAIL_FOOT.map((item) => (
              <RailLink key={item.to} item={item} />
            ))}
          </nav>
        </div>

        <div className="frame">
          {/* Provenance bar: what this dataset is, stated on every screen. */}
          <div className="bar bar--provenance mono">
            <span className="bar__tag">
              <span aria-hidden="true">◆</span> DATASET
            </span>
            {info ? (
              <span className="bar__scope">
                ANALYSIS · {info.season_from}–{info.season_to} · {info.results.toLocaleString()} race
                classifications · {info.seasons} seasons · {info.drivers} drivers · {info.constructors} constructors ·{" "}
                {info.circuits} circuits
              </span>
            ) : (
              <span className="bar__scope">ANALYSIS · loading coverage…</span>
            )}
            <span className="bar__source">SOURCE · results.csv · Ergast-derived</span>
            <span className={`bar__status bar__status--${health.error ? "down" : info ? "ok" : "wait"}`}>
              <span aria-hidden="true">●</span> {health.error ? "api unreachable" : info ? "healthy" : "connecting"}
            </span>
          </div>

          {/* Context bar: where you are, and the one global control. */}
          <div className="bar bar--context">
            <span className="bar__crumb">{crumb}</span>
            <span className="bar__sep" aria-hidden="true">
              /
            </span>
            <span className="bar__sub mono">
              {info ? `${info.seasons} seasons · ${info.races} races · static dataset` : " "}
            </span>
            <button className="bar__search" onClick={() => palette.setOpen(true)}>
              <span className="bar__label">Search drivers, constructors, circuits…</span>
              <span className="mono bar__kbd">⌘K</span>
            </button>
          </div>

          <main id="main" className="main" tabIndex={-1}>
            <Outlet />

            <footer className="page-foot mono">
              <span>SOURCE · results.csv</span>
              {info && (
                <>
                  <span>
                    COVERAGE · {info.season_from}–{info.season_to}
                  </span>
                  <span>
                    {info.races} RACES · {info.results.toLocaleString()} CLASSIFICATIONS
                  </span>
                  {/* Stated plainly and permanently: this is a historical dataset. */}
                  <span>STATIC DATASET · NOT LIVE TIMING</span>
                </>
              )}
            </footer>
          </main>
        </div>
      </div>

      <CommandPalette open={palette.open} onClose={() => palette.setOpen(false)} />
    </>
  );
}
