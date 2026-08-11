/**
 * Rail icons, traced from the design mockup (`design/F1 Dashboard.dc.html`,
 * 16px on a 24-unit grid, 1.75 stroke, `currentColor`).
 *
 * Inline rather than an icon package: there are ten of them, they are the
 * mockup's own paths, and a dependency would ship several hundred more.
 */
const box = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  "aria-hidden": true,
} as const;

export const Icons = {
  overview: () => (
    <svg {...box}>
      <rect x="3" y="3" width="7" height="9" />
      <rect x="14" y="3" width="7" height="5" />
      <rect x="14" y="12" width="7" height="9" />
      <rect x="3" y="16" width="7" height="5" />
    </svg>
  ),
  drivers: () => (
    <svg {...box}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 4-7 8-7s8 3 8 7" />
    </svg>
  ),
  constructors: () => (
    <svg {...box}>
      <path d="M3 12h4l2-4h6l2 4h4" />
      <circle cx="7" cy="16" r="2" />
      <circle cx="17" cy="16" r="2" />
    </svg>
  ),
  circuits: () => (
    <svg {...box}>
      <path d="M4 12c0-4 3-6 8-6s8 2 8 6-3 6-8 6-8-2-8-6z" />
    </svg>
  ),
  races: () => (
    <svg {...box}>
      <path d="M3 6h18M3 12h18M3 18h18" />
      <circle cx="6" cy="6" r="1" fill="currentColor" />
      <circle cx="10" cy="12" r="1" fill="currentColor" />
      <circle cx="14" cy="18" r="1" fill="currentColor" />
    </svg>
  ),
  seasons: () => (
    <svg {...box}>
      <rect x="3" y="5" width="18" height="16" rx="1" />
      <path d="M3 9h18M8 3v4M16 3v4" />
    </svg>
  ),
  insights: () => (
    <svg {...box}>
      <path d="M12 2L2 20h20L12 2z" />
      <path d="M12 10v4M12 17v.5" />
    </svg>
  ),
  records: () => (
    <svg {...box}>
      <path d="M6 3h12v6a6 6 0 0 1-12 0V3z" />
      <path d="M6 6H3v2a3 3 0 0 0 3 3M18 6h3v2a3 3 0 0 1-3 3M10 21h4M9 21v-4h6v4" />
    </svg>
  ),
  cars: () => (
    <svg {...box}>
      <path d="M4 14l1.5-4.5A3 3 0 0 1 8.4 7.5h7.2a3 3 0 0 1 2.9 2L20 14" />
      <path d="M3 14h18v3a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1H6v1a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3z" />
      <circle cx="7.5" cy="16.5" r=".8" />
      <circle cx="16.5" cy="16.5" r=".8" />
    </svg>
  ),
  compare: () => (
    <svg {...box}>
      <path d="M7 3v18M17 3v18M3 8h8M13 16h8" />
    </svg>
  ),
  // The mockup's rail ends with a settings cog. There is no settings page --
  // no accounts, no preferences, nothing to configure -- so the slot holds the
  // two real destinations the rail was otherwise missing rather than a control
  // that would do nothing.
  dataset: () => (
    <svg {...box}>
      <ellipse cx="12" cy="6" rx="8" ry="3" />
      <path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </svg>
  ),
  methodology: () => (
    <svg {...box}>
      <path d="M4 4h9a3 3 0 0 1 3 3v13a2.5 2.5 0 0 0-2.5-2H4V4z" />
      <path d="M20 4h-2a2 2 0 0 0-2 2v13a2.5 2.5 0 0 1 2.5-2H20V4z" />
    </svg>
  ),
};

export type IconName = keyof typeof Icons;
