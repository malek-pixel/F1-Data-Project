import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../components/ErrorBoundary";

/**
 * The failure these cover is the white page.
 *
 * Every other error path in this app was already handled -- a failed request
 * renders an error state with a retry. A component that *threw while
 * rendering* was not, and React's default is to unmount the whole tree: no
 * message, no navigation, nothing to click. These pin the boundary that stops
 * that.
 */

function Boom(): JSX.Element {
  throw new Error("render exploded");
}

describe("ErrorBoundary", () => {
  // React logs caught render errors to console.error by design, and the
  // boundary logs its own. Silenced so a passing run is not full of red.
  beforeEach(() => vi.spyOn(console, "error").mockImplementation(() => {}));
  afterEach(() => vi.restoreAllMocks());

  it("renders children untouched when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>the real page</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("the real page")).toBeInTheDocument();
  });

  it("shows a readable message instead of unmounting to a blank page", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/could not be displayed/i)).toBeInTheDocument();
    // The point of the boundary: something is still on screen.
    expect(document.body.textContent?.trim().length).toBeGreaterThan(20);
  });

  it("offers a way out rather than leaving the reader stuck", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
  });

  it("never shows the reader the raw exception", () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(document.body.textContent).not.toMatch(/render exploded/);
  });

  it("clears when resetKey changes, so one bad route does not poison the rest", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/broken">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/could not be displayed/i)).toBeInTheDocument();

    rerender(
      <ErrorBoundary resetKey="/somewhere-else">
        <p>a different page</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("a different page")).toBeInTheDocument();
    expect(screen.queryByText(/could not be displayed/i)).not.toBeInTheDocument();
  });
});
