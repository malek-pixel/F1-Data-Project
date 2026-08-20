/** Thin API client. Every request goes through `request` so error handling
 *  and abort support are defined once. No calculations happen here. */

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    /** true when retrying could plausibly succeed (network blip, 5xx). */
    readonly retryable: boolean,
    /**
     * The server's request id for the failed call, when it sent one.
     *
     * The API attaches this to every handled failure (body `request_id`, and
     * an `X-Request-ID` header on every response). Surfacing it in the error
     * state is what makes the server-side access log usable in practice: a
     * reader can quote eight characters instead of describing what they were
     * doing and roughly when.
     */
    readonly requestId?: string,
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
    // Worded for a reader, not for whoever deployed this. In production the
    // API is same-origin, so this branch is the ordinary "your connection
    // dropped" path -- and "is the backend running?" is not a question a
    // visitor can act on. It says what failed, and what to try.
    throw new ApiError("Could not connect. Check your internet connection and try again.", 0, true);
  }

  if (!response.ok) {
    // The backend returns {detail}. When it does not -- a dead upstream, a
    // proxy error page -- fall back to something a person can act on. A bare
    // "Request failed (500)" tells the reader nothing.
    //
    // Note the dev server proxies /api, so an unreachable backend arrives here
    // as a 500/502 rather than a thrown fetch: the network-error branch below
    // only fires when the API is same-origin or CORS-blocked.
    // Same reasoning as the network branch: a visitor is not running this
    // locally. The server's own {detail} replaces this whenever it sends one,
    // and it does for every handled failure -- this is the last resort for a
    // dead upstream or a proxy error page.
    let detail =
      response.status >= 500
        ? "This data is temporarily unavailable. Please try again in a moment."
        : `That request could not be completed (${response.status}).`;
    // Header first: it is present on every response, including the ones whose
    // body is a plain-text proxy error page with no JSON to parse.
    let requestId = response.headers.get("x-request-id") ?? undefined;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
      if (typeof body?.request_id === "string") requestId = body.request_id;
    } catch {
      /* keep the fallback */
    }
    throw new ApiError(detail, response.status, response.status >= 500, requestId);
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
