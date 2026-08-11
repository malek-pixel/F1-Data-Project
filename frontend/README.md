# Frontend

React + TypeScript + Vite. Presentation only — every derived number comes from
the API, which is the single source of truth for calculations.

## Run

The backend must be running first (it serves the data this app renders):

    # repo root
    python -m backend.etl.build
    uvicorn backend.app.main:app --port 8000

    # frontend/
    npm install
    npm run dev        # http://localhost:5173, proxies /api to :8000

`npm run build` type-checks and bundles. `npm run typecheck` alone is faster.

## Structure

    src/
      components/   shell, nav, tables, states, formatting
      charts/       hand-rolled SVG charts (see note below)
      pages/        one file per explorer area
      hooks/        useApi (abortable fetch), useDebounced
      services/     API client + query-string builder
      styles/       design tokens, component CSS

## Notable decisions

**No chart library.** The charts here are bar, line and stacked-proportion.
Hand-rolled SVG is roughly the same amount of code as configuring a library,
inherits the design tokens directly, and let every chart ship an accessible
data-table fallback without fighting a wrapper.

**No CSS framework.** The mockup is a token system; `styles/tokens.css` is a
direct transcription of it. A utility framework would add a build dependency
to restate values we already have.

**No data-fetching library.** One `useApi` hook with abort-on-change covers
every call in the app. Adding a cache layer is worthwhile only if a profile
shows it is needed.

**Unavailable is a component.** `<Unavailable>` renders a metric the dataset
cannot support. Missing data is shown explicitly rather than hidden, so a
reader can tell "we do not have this" from "this happens to be zero".
