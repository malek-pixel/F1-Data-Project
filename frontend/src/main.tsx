import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { installGlobalHandlers } from "./services/reporting";
import "./styles/tokens.css";
import "./styles/app.css";

// Before the first render, so an error thrown during mount is captured too.
// `ErrorBoundary` covers render errors; this covers the two classes React
// never routes to a boundary -- a throw outside rendering, and a rejected
// promise nobody handled. See services/reporting.ts for where they go, and
// docs/OPERATIONS.md section 6 for how to make them go somewhere off-box.
installGlobalHandlers();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
