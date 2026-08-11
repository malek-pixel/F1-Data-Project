import { createContext, useContext, type ReactNode } from "react";
import { useApi } from "./useApi";
import type { Health } from "../types";

/**
 * Dataset coverage, fetched once and shared.
 *
 * Exists so no page hardcodes a dataset figure in its copy. "129 drivers" and
 * "2000-2025" written as literals are correct only until the data changes, at
 * which point the interface quietly starts lying. Everything comes from
 * /api/health instead.
 */
const DatasetContext = createContext<Health | null>(null);

export function DatasetProvider({ children }: { children: ReactNode }) {
  const { data } = useApi<Health>("/health");
  return <DatasetContext.Provider value={data}>{children}</DatasetContext.Provider>;
}

export function useDataset(): Health | null {
  return useContext(DatasetContext);
}

/** Coverage as a display string, e.g. "2000–2025". Falls back to an em dash
 *  while the request is in flight rather than to an invented range. */
export function useCoverage(): string {
  const dataset = useDataset();
  return dataset ? `${dataset.season_from}–${dataset.season_to}` : "—";
}

/** Pluralised count, e.g. "129 drivers". Renders without the number until the
 *  real figure arrives. */
export function count(value: number | undefined, noun: string): string {
  return value === undefined ? noun : `${value.toLocaleString()} ${noun}`;
}
