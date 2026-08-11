/** Thin API client. Every request goes through `request` so error handling
 *  and abort support are defined once. No calculations happen here. */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** true when retrying could plausibly succeed (network blip, 5xx). */
    readonly retryable: boolean,
  ) {
    super(message);
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError("Could not reach the API. Is the backend running?", 0, true);
  }

  if (!response.ok) {
    // The backend returns {detail}. When it does not -- a dead upstream, a
    // proxy error page -- fall back to something a person can act on. A bare
    // "Request failed (500)" tells the reader nothing.
    //
    // Note the dev server proxies /api, so an unreachable backend arrives here
    // as a 500/502 rather than a thrown fetch: the network-error branch below
    // only fires when the API is same-origin or CORS-blocked.
    let detail =
      response.status >= 500
        ? "The API is not responding. If you are running this locally, check the backend is started."
        : `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the fallback */
    }
    throw new ApiError(detail, response.status, response.status >= 500);
  }
  return response.json() as Promise<T>;
}

/** Build a query string, dropping empty values so URLs stay clean. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(`/api${path}`, signal),
};
