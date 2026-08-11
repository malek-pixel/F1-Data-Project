import { NavLink, Outlet } from "react-router-dom";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { useApi } from "../hooks/useApi";
import type { Health } from "../types";

interface NavSection {
  group: string;
  links: { to: string; label: string; end?: boolean }[];
}

/** Information architecture, taken from the mockup's section index. */
const NAV: NavSection[] = [
  {
    group: "OVERVIEW",
    links: [{ to: "/", label: "Home", end: true }],
  },
  {
    group: "ANALYZE",
    links: [
      { to: "/drivers", label: "Drivers" },
      { to: "/constructors", label: "Constructors" },
      { to: "/circuits", label: "Circuits" },
      { to: "/races", label: "Races" },
      { to: "/seasons", label: "Seasons" },
    ],
  },
  {
    group: "COMPARE",
    links: [{ to: "/compare", label: "Compare" }],
  },
  {
    group: "INSIGHTS",
    links: [
      { to: "/insights", label: "Insights" },
      { to: "/records", label: "Records" },
    ],
  },
  {
    group: "LIBRARIES",
    links: [{ to: "/cars", label: "Cars" }],
  },
  {
    group: "DATA",
    links: [
      { to: "/dataset", label: "Dataset" },
      { to: "/methodology", label: "Methodology" },
    ],
  },
];

export function Shell() {
  const palette = useCommandPalette();
  const health = useApi<Health>("/health");

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <div className="shell">
        <div className="sidebar">
          <div className="sidebar__brand">
            <img src="/f1-logo.png" alt="" />
            <div>
              <div style={{ fontSize: 13, fontWeight: 600 }}>F1 Stats</div>
              <div className="mono" style={{ fontSize: 10, color: "var(--text-faint)" }}>
                ANALYST TOOL
              </div>
            </div>
          </div>

          <nav aria-label="Primary">
            {NAV.map((section) => (
              <div key={section.group}>
                <div className="nav__group mono">{section.group}</div>
                {section.links.map((link) => (
                  <NavLink key={link.to} to={link.to} end={link.end} className="nav__link">
                    {link.label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          <div style={{ padding: "16px 24px 0" }}>
            <button className="btn" style={{ width: "100%" }} onClick={() => palette.setOpen(true)}>
              Search <span className="mono" style={{ color: "var(--text-faint)" }}>⌘K</span>
            </button>
          </div>
        </div>

        <main id="main" className="main" tabIndex={-1}>
          <Outlet />

          <footer
            style={{
              marginTop: 48,
              paddingTop: 16,
              borderTop: "1px solid var(--border)",
              display: "flex",
              gap: 16,
              flexWrap: "wrap",
              fontSize: 11,
              color: "var(--text-faint)",
            }}
            className="mono"
          >
            <span>SOURCE · results.csv</span>
            {health.data && (
              <>
                <span>
                  COVERAGE · {health.data.season_from}–{health.data.season_to}
                </span>
                <span>{health.data.races} RACES · {health.data.results.toLocaleString()} CLASSIFICATIONS</span>
                {/* Stated plainly and permanently: this is a historical dataset. */}
                <span>STATIC DATASET · NOT LIVE TIMING</span>
              </>
            )}
          </footer>
        </main>
      </div>

      <CommandPalette open={palette.open} onClose={() => palette.setOpen(false)} />
    </>
  );
}
