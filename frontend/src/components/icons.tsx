import {
  Award,
  Car,
  Database,
  Flag,
  GitCompare,
  HardHat,
  LayoutDashboard,
  Route,
  Search,
  Trophy,
  Calendar,
  type LucideProps,
} from "lucide-react";

/**
 * Rail icons.
 *
 * One family, drawn on one grid, at one stroke width.
 *
 * This file used to hold three families at once: five glyphs traced from the
 * mockup (stroked, 24-unit grid, 1.75), five solid-fill glyphs pasted from
 * SVG Repo (four different viewBoxes, 18px, no stroke at all), and one stroked
 * path at 2.0 -- while `SearchField` separately imported from lucide-react. A
 * filled helmet next to a hairline calendar is the single most visible
 * inconsistency an interface can have, because the rail is on every screen.
 *
 * Lucide was already a dependency and already on screen in the search field,
 * so adopting it here removes the mixture rather than adding a fourth family,
 * and it costs nothing: the icons tree-shake individually.
 *
 * Sizing and stroke are set once, here, so no caller can drift.
 */
/**
 * `absoluteStrokeWidth` is what makes this a constant: without it Lucide
 * scales the stroke with the box, so a 14px icon and an 18px icon drawn from
 * the same set land at different visual weights. Exported so every other
 * Lucide call site in the app renders at the same 1.75px as the rail.
 */
export const ICON: LucideProps = {
  size: 18,
  strokeWidth: 1.75,
  absoluteStrokeWidth: true,
  "aria-hidden": true,
};

/**
 * Semantics are unchanged from the icons these replace, so nothing a returning
 * user learned about the rail is invalidated:
 *
 *   drivers      helmet, not a person -- these are race entrants, not accounts
 *   constructors trophy, as before: the constructors' championship
 *   circuits     a winding route, matching the track outlines the pages show
 *   records      a rosette, distinct in silhouette from the constructors' cup
 */
export const Icons = {
  overview: (p: LucideProps) => <LayoutDashboard {...ICON} {...p} />,
  drivers: (p: LucideProps) => <HardHat {...ICON} {...p} />,
  constructors: (p: LucideProps) => <Trophy {...ICON} {...p} />,
  circuits: (p: LucideProps) => <Route {...ICON} {...p} />,
  races: (p: LucideProps) => <Flag {...ICON} {...p} />,
  seasons: (p: LucideProps) => <Calendar {...ICON} {...p} />,
  records: (p: LucideProps) => <Award {...ICON} {...p} />,
  cars: (p: LucideProps) => <Car {...ICON} {...p} />,
  compare: (p: LucideProps) => <GitCompare {...ICON} {...p} />,
  // The mockup's rail ends with a settings cog. There is no settings page --
  // no accounts, no preferences, nothing to configure -- so the slot holds the
  // two real destinations the rail was otherwise missing rather than a control
  // that would do nothing.
  search: (p: LucideProps) => <Search {...ICON} {...p} />,
  dataset: (p: LucideProps) => <Database {...ICON} {...p} />,
};

export type IconName = keyof typeof Icons;
