import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../services/api";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  reload: () => void;
}

/**
 * Fetch `path` whenever it changes. In-flight requests are aborted on change
 * or unmount, so a slow response for an old path can never overwrite a newer
 * one -- the classic stale-render bug in search and filter UIs.
 *
 * `data` is also cleared when `path` changes, which is the other half of the
 * same bug and was missing. Aborting only stops the OLD response from
 * arriving; it does not discard the old ANSWER. A component holding several
 * of these hooks resolves them independently, so on /drivers/1 -> /drivers/2
 * the masthead could render driver 2 while a sibling cell still showed
 * driver 1's number -- a wrong figure under a correct name, with nothing to
 * indicate it. Callers that want the previous value to persist across a
 * refetch should hold it themselves.
 *
 * Pass `path = null` to skip fetching (e.g. a comparison with only one side
 * chosen yet).
 */
export function useApi<T>(path: string | null): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (path === null) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setData(null);
    setLoading(true);
    setError(null);
    api
      .get<T>(path, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause : new ApiError("Unexpected error", 0, true));
        setLoading(false);
      });

    return () => controller.abort();
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, reload };
}

/** Debounce a rapidly-changing value (search input) before it reaches the API. */
export function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
