import { Component, type ErrorInfo, type ReactNode } from "react";
import { EmptyState } from "./States";

/**
 * Catches a render-time throw and shows something a reader can act on.
 *
 * WHY THIS EXISTS
 * ---------------
 * `Async` already handles a *request* that fails. Nothing handled a component
 * that throws while rendering, and React's default for an uncaught render
 * error is to unmount the entire tree -- a white page, no message, no
 * navigation, no way back except the browser's own reload. That is the one
 * outcome the rest of this project's error handling exists to avoid, and it
 * was the only path still able to produce it.
 *
 * Deliberately a class: `componentDidCatch` has no hook equivalent, and
 * inventing one with a library would be a dependency to solve a solved
 * problem.
 *
 * SCOPE
 * -----
 * Mounted inside the shell rather than around it, so the chrome -- navigation,
 * search, the dataset banner -- survives the failure and the reader can leave
 * the broken screen without reloading. `resetKey` changes on navigation, which
 * clears the error: a throw on one route should not poison every route after
 * it.
 *
 * The message stays generic. The real error goes to the console, where a
 * developer looks, and would mean nothing to anybody else.
 */

interface Props {
  children: ReactNode;
  /** Changing this clears a caught error -- pass the current pathname. */
  resetKey?: string;
}

interface State {
  failed: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept, not removed as "debug logging": this is the only record that a
    // render failed. There is no error reporting in this project yet, so the
    // console is the whole story -- see docs/OPERATIONS.md §6.
    console.error("Render failed:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <EmptyState
        title="This screen could not be displayed"
        body="Something went wrong rendering this page. The rest of the app still works — use the navigation to go elsewhere, or reload to try again."
        action={
          <button className="btn btn--primary" onClick={() => window.location.reload()}>
            Reload
          </button>
        }
      />
    );
  }
}
