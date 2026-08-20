import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  installGlobalHandlers,
  report,
  resetForTests,
  setReporter,
  type ErrorReport,
} from "../services/reporting";

/**
 * What these pin down.
 *
 * The value of this module is that a frontend failure reaches somebody. That
 * property fails silently by construction -- if capture stops working, the
 * symptom is an absence of reports, which looks exactly like an absence of
 * bugs. So the cases below assert the things that would quietly stop being
 * true: that the two React-invisible failure paths are covered at all, that a
 * loop cannot flood the sink, and that the reporter can never itself become
 * the error.
 */

describe("services/reporting", () => {
  let sink: ErrorReport[];

  beforeEach(() => {
    resetForTests();
    sink = [];
    setReporter((entry) => sink.push(entry));
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    resetForTests();
    vi.restoreAllMocks();
  });

  it("passes a captured error to the installed sink", () => {
    report("render", new Error("boom"));
    expect(sink).toHaveLength(1);
    expect(sink[0].message).toBe("boom");
    expect(sink[0].source).toBe("render");
    expect(sink[0].stack).toBeTruthy();
  });

  it("records the route, which is the field that makes a report actionable", () => {
    report("render", new Error("boom"));
    expect(sink[0].path).toBe(window.location.pathname);
  });

  it("survives a throw that is not an Error", () => {
    // `throw "a string"` is legal, and a rejected promise's reason is
    // frequently not an Error. Assuming `.message` would crash the reporter
    // on exactly the input it exists to record.
    report("window", "a bare string");
    report("unhandledrejection", { code: 42 });
    report("window", null);
    expect(sink.map((entry) => entry.message)).toEqual([
      "a bare string",
      '{"code":42}',
      "null",
    ]);
  });

  it("reports a repeated error once, so a render loop cannot flood the sink", () => {
    const error = new Error("same bug every frame");
    for (let i = 0; i < 200; i += 1) report("render", error);
    expect(sink).toHaveLength(1);
  });

  it("still distinguishes genuinely different errors", () => {
    report("render", new Error("first"));
    report("render", new Error("second"));
    expect(sink).toHaveLength(2);
  });

  it("never lets a failing reporter become a second error", () => {
    // A reporting path that can throw would take the boundary down with it --
    // turning a handled render error into the white page the boundary exists
    // to prevent.
    setReporter(() => {
      throw new Error("the sink is down");
    });
    expect(() => report("render", new Error("original"))).not.toThrow();
  });

  it("works with no reporter installed at all", () => {
    setReporter(null);
    expect(() => report("render", new Error("nowhere to go"))).not.toThrow();
  });

  it("captures a global throw that React never routes to a boundary", () => {
    const teardown = installGlobalHandlers(window);
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("outside react") }));
    teardown();

    expect(sink).toHaveLength(1);
    expect(sink[0].source).toBe("window");
    expect(sink[0].message).toBe("outside react");
  });

  it("captures a rejected promise nobody handled", () => {
    const teardown = installGlobalHandlers(window);
    const event = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.defineProperty(event, "reason", { value: new Error("dropped promise") });
    window.dispatchEvent(event);
    teardown();

    expect(sink).toHaveLength(1);
    expect(sink[0].source).toBe("unhandledrejection");
    expect(sink[0].message).toBe("dropped promise");
  });

  it("removes its listeners on teardown", () => {
    // A detached target, not `window`: dispatching an unhandled `error` event
    // at the real window is itself an uncaught exception, so asserting on the
    // real one would make this test fail the run it is meant to keep clean.
    const target = new EventTarget();
    const teardown = installGlobalHandlers(target);
    teardown();
    target.dispatchEvent(new ErrorEvent("error", { error: new Error("after teardown") }));
    expect(sink).toHaveLength(0);
  });
});
