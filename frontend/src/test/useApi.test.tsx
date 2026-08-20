import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useApi } from "../hooks/useApi";

afterEach(() => vi.unstubAllGlobals());

/** A fetch whose responses are keyed by path, each resolvable on demand. */
function deferredFetch() {
  const pending = new Map<string, (body: unknown) => void>();
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      return new Promise((resolve) => {
        pending.set(url, (body) =>
          resolve(
            new Response(JSON.stringify(body), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }),
          ),
        );
      });
    }),
  );
  return {
    resolve: async (fragment: string, body: unknown) => {
      const key = [...pending.keys()].find((k) => k.includes(fragment));
      if (!key) throw new Error(`no in-flight request matching ${fragment}`);
      await act(async () => {
        pending.get(key)!(body);
      });
    },
  };
}

describe("useApi", () => {
  it("does not carry one entity's answer over to the next", async () => {
    // Aborting the old request stops the old RESPONSE arriving; it does not
    // discard the old ANSWER. A page holding several of these hooks resolves
    // them independently, so without clearing `data` the masthead could show
    // driver 2 while a sibling cell still showed driver 1's number.
    const server = deferredFetch();
    const { result, rerender } = renderHook(({ path }) => useApi<{ qualifying_p1: number }>(path), {
      initialProps: { path: "/drivers/1/qualifying" },
    });

    await server.resolve("/drivers/1/qualifying", { qualifying_p1: 104 });
    await waitFor(() => expect(result.current.data).toEqual({ qualifying_p1: 104 }));

    rerender({ path: "/drivers/2/qualifying" });

    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);

    await server.resolve("/drivers/2/qualifying", { qualifying_p1: 1 });
    await waitFor(() => expect(result.current.data).toEqual({ qualifying_p1: 1 }));
  });

  it("reports a null path as resolved-empty, not as loading forever", async () => {
    const { result } = renderHook(() => useApi<unknown>(null));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
