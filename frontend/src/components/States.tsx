import type { ReactNode } from "react";
import { AlertTriangle, Inbox } from "lucide-react";
import type { ApiError } from "../services/api";
import { ICON } from "./icons";

/** Skeleton block sized to the content it replaces, so nothing shifts on load. */
export function Skeleton({
  height = 20,
  width = "100%",
}: {
  /** Accepts a percentage so a chart skeleton's bars can be sized against the
   *  plot area rather than against a guessed pixel height. */
  height?: number | string;
  width?: number | string;
}) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

/**
 * What shape the skeleton should take.
 *
 * Every one of the app's 29 async surfaces used to render the same stack of
 * grey bars, whether it was about to become a card grid, a nine-column table
 * or a chart. Two costs to that: the placeholder shifts the layout when the
 * real content arrives at a different height, and a loading state that does
 * not resemble what is loading reads as a generic spinner with extra steps.
 *
 * The variants below are deliberately crude -- they suggest the *shape* of
 * what is coming, not a facsimile of it. A skeleton that mimics content too
 * precisely is worse: it promises a layout the data may not fill.
 */
export type LoadingVariant = "rows" | "cards" | "table" | "chart" | "stats";

export function LoadingState({
  label = "Loading data",
  rows = 4,
  variant = "rows",
}: {
  label?: string;
  rows?: number;
  variant?: LoadingVariant;
}) {
  // One live region per surface, announced once. The visual skeleton is
  // aria-hidden, so a screen reader hears "Loading data" rather than a
  // description of decorative boxes.
  const announce = (
    <span className="sr-only" role="status" aria-live="polite">
      {label}
    </span>
  );

  if (variant === "cards") {
    return (
      <div className="skeleton-grid">
        {announce}
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton-card" aria-hidden="true">
            <Skeleton height={78} />
            <Skeleton height={13} width="62%" />
            <Skeleton height={11} width="40%" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div className="skeleton-table" aria-hidden="true">
        {announce}
        <div className="skeleton-table__head">
          <Skeleton height={10} width="22%" />
          <Skeleton height={10} width="14%" />
          <Skeleton height={10} width="10%" />
        </div>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton-table__row">
            {/* Varied widths, because a column of identical bars reads as a
                progress meter rather than as rows of different names. */}
            <Skeleton height={12} width={`${52 + ((i * 13) % 34)}%`} />
            <Skeleton height={12} width="14%" />
            <Skeleton height={12} width="10%" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "chart") {
    return (
      <div className="skeleton-chart" aria-hidden="true">
        {announce}
        <div className="skeleton-chart__plot">
          {Array.from({ length: 12 }, (_, i) => (
            <Skeleton
              key={i}
              // A fixed, non-random profile: a shuffled skeleton on every
              // render would imply the data changes between paints.
              height={`${28 + ((i * 37) % 62)}%`}
              width="100%"
            />
          ))}
        </div>
        <Skeleton height={10} width="34%" />
      </div>
    );
  }

  if (variant === "stats") {
    return (
      <div className="skeleton-stats" aria-hidden="true">
        {announce}
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton-stats__cell">
            <Skeleton height={9} width="52%" />
            <Skeleton height={26} width="70%" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      {announce}
      <div aria-hidden="true" style={{ display: "grid", gap: 8 }}>
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} height={i === 0 ? 32 : 20} />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="state">
      {/* Same frame and the same icon slot as the error state, so "nothing
          here" and "something failed" read as two states of one component
          rather than two unrelated screens. The glyph differs because the
          two situations are not the same and must not look it. */}
      <div className="state__icon state__icon--quiet" aria-hidden="true">
        <Inbox {...ICON} size={20} />
      </div>
      <div className="state__title">{title}</div>
      <p className="state__body">{body}</p>
      {action}
    </div>
  );
}

/** Error state: says what failed and whether retry is worth trying.
 *  Never shows a stack trace or a raw status code on its own. */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const canRetry = error.retryable && Boolean(onRetry);
  return (
    <div className="state state--error" role="alert">
      <div className="state__icon" aria-hidden="true">
        <AlertTriangle {...ICON} size={20} />
      </div>
      <div className="state__title">Could not load this section</div>
      <p className="state__body">{error.message}</p>
      {canRetry ? (
        <button className="btn btn--primary" onClick={onRetry}>
          Try again
        </button>
      ) : (
        /* Every error state must offer a way forward. A non-retryable failure
           previously rendered a message and a dead end -- the reader was told
           something broke and given nothing to do about it. Retrying a 4xx
           will not help, so the exit is out of the section rather than into
           it again. */
        <p className="state__hint">
          Retrying will not help with this one. The rest of the app is unaffected — use the navigation, or{" "}
          <button className="linklike" onClick={() => window.location.reload()}>
            reload the page
          </button>
          .
        </p>
      )}
      {/* The request id when the API supplied one. It is what turns "a page
          broke earlier" into one grep of the server log, and it is safe to
          show: a random token identifying a log line, not a user. */}
      {error.requestId && (
        <p className="state__ref mono">
          REF <span className="state__refid">{error.requestId}</span>
        </p>
      )}
    </div>
  );
}

/**
 * A metric the dataset cannot support.
 *
 * This is a deliberate, visible state -- not a hidden element and not a zero.
 * `why` must name the missing column, so a reader can tell "we don't have the
 * data" apart from "the value happens to be zero".
 */
export function Unavailable({ label, why }: { label: string; why: string }) {
  return (
    <div className="unavailable">
      <div className="unavailable__label mono">{label}</div>
      <div className="unavailable__value">Not available in dataset</div>
      <div className="unavailable__why">{why}</div>
    </div>
  );
}

/**
 * Renders whichever of loading / error / empty / content applies.
 *
 * Sections use this individually rather than gating a whole page, so one
 * failing panel never blanks a page whose other panels loaded fine.
 */
export function Async<T>({
  state,
  children,
  empty,
  loadingRows,
  loadingVariant,
}: {
  state: { data: T | null; loading: boolean; error: ApiError | null; reload: () => void };
  children: (data: T) => ReactNode;
  empty?: { title: string; body: string };
  loadingRows?: number;
  /** Shape of the placeholder. Defaults to the original stack of bars, so
   *  every existing call site keeps its current behaviour until it opts in. */
  loadingVariant?: LoadingVariant;
}) {
  if (state.loading) return <LoadingState rows={loadingRows} variant={loadingVariant} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.data === null) return null;
  if (empty && Array.isArray(state.data) && state.data.length === 0) {
    return <EmptyState title={empty.title} body={empty.body} />;
  }
  return <>{children(state.data)}</>;
}
