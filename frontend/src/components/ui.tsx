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

