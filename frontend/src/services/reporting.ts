/**
 * Client-side error capture: one place every frontend failure passes through.
 *
 * WHY THIS EXISTS
 * ---------------
 * `ErrorBoundary` catches a component that throws *while rendering*. That is
 * one of three ways this app can fail, and it was the only one anything
 * noticed. The other two went nowhere at all:
 *
 *   * an error thrown in an event handler, a `setTimeout`, or any code React
 *     is not rendering at the time -- React does not route these to a
 *     boundary, so they reached `window.onerror` and stopped;
 *   * a rejected promise nobody awaited -- a `.then()` chain with no `.catch`,
 *     an aborted-but-not-handled fetch -- which surfaces only as
 *     `unhandledrejection`.
 *
 * Both are now captured here, alongside the boundary's render errors, so the
 * three paths converge on a single function instead of three conventions.
 *
 * WHAT THIS DOES NOT DO, AND SAYING IT PLAINLY
 * --------------------------------------------
 * **By default these reports go to the browser console and no further.** They
 * are captured, normalised and de-duplicated -- they are not transmitted. A
 * console message in a visitor's browser tells nobody anything, and this file
 * would be dishonest if it implied otherwise.
 *
 * Transmitting them needs a sink, and choosing one is a deployment decision
 * rather than a code decision, so it is a seam rather than a hardcoded vendor:
 * call `setReporter` once at startup and every captured error flows to it.
 * See `docs/OPERATIONS.md` section 6 for the two supported options and their
 * trade-offs.
 *
 * No SDK is imported here. `@sentry/browser` is not a dependency of this
 * project, and adding one to ship a seam that a deployment may never use
 * would put ~30 KB in every visitor's bundle to solve a problem nobody has
 * had yet.
 */

/** A captured failure, normalised across the three paths that produce one. */
export interface ErrorReport {
  /** Where it came from -- render, a global throw, or a dropped promise. */
  source: "render" | "window" | "unhandledrejection";
  message: string;
  stack?: string;
  /** React's component stack. Only present for `source: "render"`. */
  componentStack?: string;
  /** The route the reader was on. The single most useful field in practice. */
  path: string;
  timestamp: string;
}

type Reporter = (report: ErrorReport) => void;

/**
 * Install the sink. Called once at startup, before the app renders.
 *
 * Deliberately a setter rather than a build-time import: it keeps the vendor
 * choice (or the absence of one) out of every module that can fail.
 */
let reporter: Reporter | null = null;
export function setReporter(next: Reporter | null): void {
  reporter = next;
}

/**
 * Bound at 50. A render loop can throw thousands of times a second, and an
 * unbounded set would turn an error into a memory leak on top of an error.
 */
const seen = new Set<string>();
const MAX_TRACKED = 50;

function isDuplicate(report: ErrorReport): boolean {
  // Keyed on message + first stack frame, not the timestamp: the same bug
  // firing on every re-render is one problem, and reporting it 400 times
  // makes the log less useful rather than more.
  const key = `${report.source}|${report.message}|${(report.stack ?? "").split("\n")[1] ?? ""}`;
  if (seen.has(key)) return true;
  if (seen.size >= MAX_TRACKED) seen.clear();
  seen.add(key);
  return false;
}

/** Turn whatever was thrown into something with a message and a stack.
 *
 *  `throw "a string"` is legal JavaScript and `reason` on a rejected promise
 *  is frequently not an Error at all, so this cannot assume `error.message`
 *  exists. */
function describe(thrown: unknown): { message: string; stack?: string } {
  if (thrown instanceof Error) {
    return { message: thrown.message || thrown.name, stack: thrown.stack };
  }
  if (typeof thrown === "string") return { message: thrown };
  try {
    return { message: JSON.stringify(thrown) };
  } catch {
    return { message: String(thrown) };
  }
}

/**
 * The single entry point. Every failure path in the app calls this.
 *
 * Never throws. A reporting function that can itself fail would turn one
 * error into two and could take the boundary down with it -- so the sink is
 * called inside a try/catch and its failure is swallowed after a console note.
 */
export function report(
  source: ErrorReport["source"],
  thrown: unknown,
  extra: { componentStack?: string } = {},
): ErrorReport | null {
  const { message, stack } = describe(thrown);
  const entry: ErrorReport = {
    source,
    message,
    stack,
    componentStack: extra.componentStack,
    path: typeof window !== "undefined" ? window.location.pathname : "",
    timestamp: new Date().toISOString(),
  };

  if (isDuplicate(entry)) return null;

  // Kept unconditionally, not only when no reporter is installed: during
  // development the console IS the monitoring, and in production it is what a
  // reader can screenshot when they tell someone the page broke.
  console.error(`[${source}] ${message}`, entry);

  try {
    reporter?.(entry);
  } catch (failure) {
    console.error("Error reporter itself failed:", failure);
  }
  return entry;
}

/**
 * Catch the two classes of failure React never sees.
 *
 * Returns a teardown function so tests can install and remove this cleanly
 * rather than leaking listeners across cases.
 *
 * Typed as `EventTarget` rather than `Window` so a test can install onto a
 * detached target. Dispatching an unhandled `error` event at the real
 * `window` with no listener attached is itself an uncaught exception, so a
 * test proving teardown works would otherwise have to cause the failure it is
 * checking is no longer captured.
 */
export function installGlobalHandlers(target: EventTarget = window): () => void {
  const onError = (event: Event) => {
    const error = event as ErrorEvent;
    report("window", error.error ?? error.message);
  };
  const onRejection = (event: Event) => {
    report("unhandledrejection", (event as PromiseRejectionEvent).reason);
  };

  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}

/** Test seam. Clears the de-duplication memory between cases. */
export function resetForTests(): void {
  seen.clear();
  reporter = null;
}
