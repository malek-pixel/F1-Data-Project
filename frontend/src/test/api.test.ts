import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, qs } from "../services/api";

afterEach(() => vi.unstubAllGlobals());

const respond = (body: unknown, init: ResponseInit = {}) =>
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
        ...init,
      }),
    ),
  );

describe("qs", () => {
  it("drops empty values so URLs stay clean", () => {
    expect(qs({ search: "", sort: "wins", season: null, limit: undefined })).toBe("?sort=wins");
  });

  it("keeps a genuine zero", () => {
    expect(qs({ offset: 0 })).toBe("?offset=0");
  });

  it("encodes special characters", () => {
    expect(qs({ search: "Pérez & co" })).toBe("?search=P%C3%A9rez+%26+co");
  });

  it("returns an empty string when nothing survives", () => {
    expect(qs({ a: "", b: null })).toBe("");
  });
});

describe("api error handling", () => {
  it("surfaces the backend's structured detail", async () => {
    respond({ detail: "No driver with id 999" }, { status: 404 });
    await expect(api.get("/drivers/999")).rejects.toMatchObject({
      message: "No driver with id 999",
      status: 404,
      retryable: false,
    });
  });

  it("marks 5xx as retryable and 4xx as not", async () => {
    respond({ detail: "Data store unavailable." }, { status: 503 });
    await expect(api.get("/x")).rejects.toMatchObject({ retryable: true });

    respond({ detail: "bad input" }, { status: 422 });
    await expect(api.get("/x")).rejects.toMatchObject({ retryable: false });
  });

  it("gives an actionable message when the upstream is dead, not a bare status", async () => {
    // The dev server proxies /api, so an unreachable backend arrives as a 502
    // with an HTML body -- not a thrown fetch.
    respond("<html>502 Bad Gateway</html>", { status: 502 });
    const error = await api.get<never>("/x").catch((e: unknown) => e as ApiError);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toMatch(/temporarily unavailable/);
    // Never leaks the HTML body or a JSON parse error to the user.
    expect(error.message).not.toMatch(/html|SyntaxError/i);
  });

  it("keeps a bare status for 4xx bodies that carry no detail", async () => {
    respond("nope", { status: 418 });
    const error = await api.get<never>("/x").catch((e: unknown) => e as ApiError);
    expect(error.message).toBe("That request could not be completed (418).");
  });

  it("explains a dropped connection in terms a reader can act on", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.get<never>("/health").catch((e: unknown) => e as ApiError);
    expect(error).toMatchObject({ retryable: true });
    expect(error.message).toBe("Could not connect. Check your internet connection and try again.");
    // The copy a visitor sees must not ask them about servers they do not run.
    expect(error.message).not.toMatch(/backend|API|server|localhost/i);
  });

  it("returns parsed JSON on success", async () => {
    respond({ status: "ok", live_data: false });
    await expect(api.get("/health")).resolves.toEqual({ status: "ok", live_data: false });
  });
});
