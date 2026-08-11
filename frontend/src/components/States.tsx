import type { ReactNode } from "react";
import type { ApiError } from "../services/api";

/** Skeleton block sized to the content it replaces, so nothing shifts on load. */
export function Skeleton({ height = 20, width = "100%" }: { height?: number; width?: number | string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

export function LoadingState({ label = "Loading data", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" style={{ display: "grid", gap: 8 }}>
      <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
        {label}
      </span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={i === 0 ? 32 : 20} />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state__title">{title}</div>
      <p className="state__body">{body}</p>
      {action}
    </div>
  );
}

/** Error state: says what failed and whether retry is worth trying.
 *  Never shows a stack trace or a raw status code on its own. */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="state" role="alert">
      <div className="state__title">Could not load this section</div>
      <p className="state__body">{error.message}</p>
      {error.retryable && onRetry && (
        <button className="btn btn--primary" onClick={onRetry}>
          Try again
        </button>
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
}: {
  state: { data: T | null; loading: boolean; error: ApiError | null; reload: () => void };
  children: (data: T) => ReactNode;
  empty?: { title: string; body: string };
  loadingRows?: number;
}) {
  if (state.loading) return <LoadingState rows={loadingRows} />;
  if (state.error) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (state.data === null) return null;
  if (empty && Array.isArray(state.data) && state.data.length === 0) {
    return <EmptyState title={empty.title} body={empty.body} />;
  }
  return <>{children(state.data)}</>;
}
