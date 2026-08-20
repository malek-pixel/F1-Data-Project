import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  sub,
  actions,
}: {
  eyebrow?: string;
  title: string;
  sub?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <div className="page-header__eyebrow mono">{eyebrow}</div>}
        <h1>{title}</h1>
        {sub && <div className="page-header__sub">{sub}</div>}
      </div>
      {actions && <div className="controls" style={{ margin: 0 }}>{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="section-title">
      <h2>{children}</h2>
      <div className="section-title__rule" />
      {aside && <div className="mono" style={{ fontSize: 11, color: "var(--text-dim)" }}>{aside}</div>}
    </div>
  );
}

export function Card({ title, label, children }: { title?: string; label?: string; children: ReactNode }) {
  return (
    <section className="card">
      {label && <div className="card__label mono">{label}</div>}
      {title && <h3 className="card__title">{title}</h3>}
      {children}
    </section>
  );
}

/**
 * Single metric. `value` of null renders an em dash rather than 0, and `note`
 * carries the caveat (e.g. small sample) so the number is never bare.
 */
export function StatCard({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "warning";
}) {
  return (
    <div className="stat">
      <div className="stat__label mono">{label}</div>
      <div className="stat__value mono" style={tone === "warning" ? { color: "var(--warning)" } : undefined}>
        {value}
      </div>
      {note && <div className="stat__note">{note}</div>}
    </div>
  );
}

export function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone?: "warning" | "info" | "accent";
}) {
  return <span className={`badge${tone ? ` badge--${tone}` : ""}`}>{children}</span>;
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          className="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Pagination({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <nav className="pagination" aria-label="Pagination">
      <button className="btn" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
        Previous
      </button>
      <span aria-live="polite" className="mono" style={{ fontSize: 12 }}>
        {from}–{to} of {total.toLocaleString()}
      </span>
      <button className="btn" disabled={to >= total} onClick={() => onChange(offset + limit)}>
        Next
      </button>
    </nav>
  );
}

/* --------------------------------------------------------------------------
   Mockup layout primitives
   --------------------------------------------------------------------------
   The design (`design/F1 Dashboard.dc.html`) builds every screen from the same
   four shapes: a bordered panel, a hairline-divided head, a cell grid, and a
   pending slot for a field the dataset does not carry yet. Defining them once
   is what keeps fifteen screens looking like one product.
   ------------------------------------------------------------------------ */

/** Bordered surface. `pad` for prose panels; omit for panels holding a grid. */
export function Panel({
  children,
  pad,
  className = "",
}: {
  children: ReactNode;
  pad?: boolean;
  className?: string;
}) {
  return <div className={`panel${pad ? " panel--pad" : ""} ${className}`.trim()}>{children}</div>;
}

/** Panel header: title left, meta right, hairline under. */
export function PaneHead({ title, meta, flush }: { title: ReactNode; meta?: ReactNode; flush?: boolean }) {
  return (
    <div className={`pane__head${flush ? " pane__head--flush" : ""}`}>
      {/* A real heading, not a styled span: a panel title is the heading of
          its section, and pages like the libraries have no other h2. Without
          it a screen-reader user gets one h1 and no way to skim the page. */}
      <h2 className="pane__title">{title}</h2>
      {meta && <span className="pane__meta mono">{meta}</span>}
    </div>
  );
}

/**
 * Equal-width cell grid with shared hairlines, as used by every KPI strip.
 *
 * The column count travels as a custom property, never as an inline
 * `grid-template-columns`. An inline track list outranks every media query in
 * the stylesheet, which pinned detail pages to six columns on a phone: six
 * 48px cells whose labels and values were clipped to a few pixels each. As a
 * variable it sets the desktop count and the breakpoints still get to override.
 */
export function CellGrid({ cols, children }: { cols: number; children: ReactNode }) {
  return (
    <div className="kpi-strip" style={{ ["--kpi-cols" as string]: cols }}>
      {children}
    </div>
  );
}

/** One measured cell. Matches the mockup's 11px label / 28px value pairing. */
export function Cell({
  label,
  value,
  sub,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  note?: ReactNode;
  tone?: "warning";
}) {
  return (
    <div className="kpi">
      <div className="kpi__label mono">{label}</div>
      <div className="kpi__value-row">
        <div className="kpi__value mono" style={tone === "warning" ? { color: "var(--warning)" } : undefined}>
          {value}
        </div>
        {sub && <div className="kpi__sub mono">{sub}</div>}
      </div>
      {note && <div className="kpi__note">{note}</div>}
    </div>
  );
}

/**
 * A field the mockup shows and the dataset does not carry.
 *
 * Rendered in place, keeping the cell's shape, rather than dropped: a reader
 * should see that the field was designed for and is genuinely absent, not
 * silently missing. `why` names the column that would supply it, so "to be
 * added" is a statement about the source and not a shrug.
 */
export function PendingCell({ label, why }: { label: string; why: string }) {
  return (
    <div className="kpi kpi--pending">
      <div className="kpi__label mono">{label}</div>
      <div className="kpi__value-row">
        <div className="kpi__value mono kpi__value--pending">—</div>
        <div className="kpi__sub mono">to be added</div>
      </div>
      <div className="kpi__note">{why}</div>
    </div>
  );
}

/**
 * A cell whose value could not be LOADED -- which is not the same thing as a
 * value the dataset does not carry, and must never be rendered as one.
 *
 * `PendingCell` makes a claim about the source ("no standings recorded for
 * this season"). When a request has failed, that claim is false: the standings
 * exist and we simply could not fetch them. Saying "to be added" there told
 * readers that 2022, 2024 and 2025 had no championship, which is exactly the
 * kind of fabricated absence this project refuses everywhere else.
 *
 * So this state says the opposite: the value is unknown right now, and the
 * reason is ours, not the data's.
 */
export function UnknownCell({ label, why }: { label: string; why: string }) {
  return (
    <div className="kpi kpi--pending">
      <div className="kpi__label mono">{label}</div>
      <div className="kpi__value-row">
        <div className="kpi__value mono kpi__value--pending">—</div>
        <div className="kpi__sub mono">unavailable</div>
      </div>
      <div className="kpi__note">{why}</div>
    </div>
  );
}

/** Inline "not in the dataset" marker for table cells. */
export function PendingValue({ title }: { title?: string }) {
  return (
    <span className="pending mono" title={title ?? "Not in the dataset yet"}>
      —
    </span>
  );
}

/** Removable filter chip, as in the mockup's active-filter rows. */
export function FilterChip({ label, onClear }: { label: string; onClear?: () => void }) {
  return (
    <span className="chip mono">
      {label}
      {onClear && (
        <button className="chip__x" onClick={onClear} aria-label={`Clear filter ${label}`}>
          ×
        </button>
      )}
    </span>
  );
}

/** Horizontal segmented control (the mockup's Table/Grid, All/Active toggles). */
export function Segmented<T extends string>({
  options,
  active,
  onChange,
  label,
}: {
  options: { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="tablist" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          role="tab"
          aria-selected={active === option.id}
          className="segmented__btn"
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
