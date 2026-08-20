import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Icons, type IconName } from "./icons";

/**
 * Primary navigation for small screens.
 *
 * WHY THIS EXISTS
 * ---------------
 * There was no mobile navigation. `.shell` is `grid-template-columns: 56px 1fr`
 * and was never redefined at any breakpoint, so the desktop icon rail --
 * a 100vh sticky column -- persisted at 375px, where it took 15% of the
 * viewport width and left content 319px. Every item in it was icon-only with
 * the label in a `title` attribute, which on touch is unreachable: there is no
 * hover to reveal it. So the app's entire primary navigation was eleven
 * unlabelled 40px glyphs in a column that also ate the page.
 *
 * That is the "don't just shrink desktop components" case exactly, and it was
 * the single largest responsive defect in the app.
 *
 * THE SHAPE
 * ---------
 * A bottom bar, because the top of a phone screen is the hardest place to
 * reach and this is the control a reader uses most. Five destinations, which
 * is the documented ceiling before targets get too narrow to hit reliably --
 * so the remaining six live behind an explicit "More" sheet rather than being
 * crammed in at 40px each.
 *
 * Every item carries an icon AND a text label. Icon-only navigation is a
 * discoverability problem on desktop and an accessibility failure on touch.
 *
 * Rendered always and hidden with CSS above 720px rather than being mounted
 * conditionally: a JS-driven breakpoint would flash the wrong navigation on
 * first paint and would need a resize listener to stay correct.
 */

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
}

/** The five that earn a permanent slot: the entry point, the two entity types
 *  most searched for, the calendar, and search itself. */
const PRIMARY: NavItem[] = [
  { to: "/", label: "Overview", icon: "overview", end: true },
  { to: "/drivers", label: "Drivers", icon: "drivers" },
  { to: "/races", label: "Races", icon: "races" },
  { to: "/seasons", label: "Seasons", icon: "seasons" },
  { to: "/search", label: "Search", icon: "search" },
];

/** Everything else, reachable in one extra tap rather than not at all. */
const MORE: NavItem[] = [
  { to: "/constructors", label: "Constructors", icon: "constructors" },
  { to: "/circuits", label: "Circuits", icon: "circuits" },
  { to: "/records", label: "Records", icon: "records" },
  { to: "/cars", label: "Cars", icon: "cars" },
  { to: "/compare", label: "Compare", icon: "compare" },
  { to: "/dataset", label: "Dataset", icon: "dataset" },
];

function Item({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const Icon = Icons[item.icon];
  return (
    <NavLink to={item.to} end={item.end} className="mnav__item" onClick={onNavigate}>
      <Icon />
      <span className="mnav__label">{item.label}</span>
    </NavLink>
  );
}

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const sheetRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);

  // Navigating away closes the sheet. Without this it stays open over the new
  // page, which reads as the tap not having worked.
  useEffect(() => setOpen(false), [pathname]);

  // Escape closes and returns focus to the control that opened it -- the same
  // contract the command palette already honours.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        moreRef.current?.focus();
      }
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!sheetRef.current?.contains(target) && !moreRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  // `aria-current` is what marks the active destination for assistive tech;
  // NavLink sets it, and the CSS marks it visually with a bar AND a colour.
  const moreActive = MORE.some((item) => pathname.startsWith(item.to));

  return (
    <nav className="mnav" aria-label="Primary">
      {open && (
        <div className="mnav__sheet" ref={sheetRef} role="group" aria-label="More destinations">
          {MORE.map((item) => (
            <Item key={item.to} item={item} onNavigate={() => setOpen(false)} />
          ))}
        </div>
      )}
      <div className="mnav__bar">
        {PRIMARY.map((item) => (
          <Item key={item.to} item={item} />
        ))}
        <button
          type="button"
          ref={moreRef}
          className="mnav__item mnav__item--more"
          aria-expanded={open}
          aria-haspopup="true"
          data-active={moreActive || undefined}
          onClick={() => setOpen((value) => !value)}
        >
          <Icons.more />
          <span className="mnav__label">More</span>
        </button>
      </div>
    </nav>
  );
}
