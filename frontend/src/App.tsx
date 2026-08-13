import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { DatasetProvider } from "./hooks/useDataset";
import { EmptyState, Skeleton } from "./components/States";
import { PageHeader } from "./components/ui";
import { Home } from "./pages/Home";

/**
 * Route-level code splitting.
 *
 * `Home` is imported eagerly -- it is what the entry URL renders, so deferring
 * it would only add a round trip to the one page everybody sees first. Every
 * other screen is fetched when it is first navigated to.
 *
 * The pairs below share a module (`Calendar` holds all four calendar screens,
 * `Data` holds two), so each `lazy()` on the same path resolves to the same
 * chunk -- naming them separately costs nothing and keeps the route table
 * readable.
 */
const EntityLibrary = lazy(() => import("./pages/EntityLibrary").then((m) => ({ default: m.EntityLibrary })));
const DriverDetail = lazy(() => import("./pages/DriverDetail").then((m) => ({ default: m.DriverDetail })));
const ConstructorDetail = lazy(() =>
  import("./pages/ConstructorDetail").then((m) => ({ default: m.ConstructorDetail })),
);
const CircuitLibrary = lazy(() => import("./pages/Circuits").then((m) => ({ default: m.CircuitLibrary })));
const CircuitDetail = lazy(() => import("./pages/Circuits").then((m) => ({ default: m.CircuitDetail })));
const RaceIndex = lazy(() => import("./pages/Calendar").then((m) => ({ default: m.RaceIndex })));
const RaceDetail = lazy(() => import("./pages/Calendar").then((m) => ({ default: m.RaceDetail })));
const SeasonIndex = lazy(() => import("./pages/Calendar").then((m) => ({ default: m.SeasonIndex })));
const SeasonDetail = lazy(() => import("./pages/Calendar").then((m) => ({ default: m.SeasonDetail })));
const Compare = lazy(() => import("./pages/Compare").then((m) => ({ default: m.Compare })));
const Records = lazy(() => import("./pages/Data").then((m) => ({ default: m.Records })));
const Dataset = lazy(() => import("./pages/Data").then((m) => ({ default: m.Dataset })));
const CarLibrary = lazy(() => import("./pages/Cars").then((m) => ({ default: m.CarLibrary })));
const Search = lazy(() => import("./pages/Search").then((m) => ({ default: m.Search })));

function NotFound() {
  return (
    <>
      <PageHeader eyebrow="404" title="Page not found" />
      <EmptyState title="Nothing here" body="That route does not exist. Use the navigation or press ⌘K to search." />
    </>
  );
}

/**
 * Shown while a route's chunk is in flight.
 *
 * The same skeleton the panels use, so a chunk fetch looks like the data
 * fetch that follows it rather than introducing a second kind of waiting.
 * On a local network this is usually a single frame.
 */
function RouteFallback() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading page…</span>
      <Skeleton height={38} width="34%" />
      <div style={{ height: 20 }} />
      {[0, 1, 2, 3, 4].map((row) => (
        <div key={row} style={{ marginBottom: 10 }}>
          <Skeleton height={22} />
        </div>
      ))}
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <DatasetProvider>
        <Routes>
          <Route element={<Shell />}>
            <Route
              index
              element={<Home />}
            />
            <Route
              path="drivers"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <EntityLibrary kind="drivers" title="Drivers" eyebrow="DRIVER LIBRARY" />
                </Suspense>
              }
            />
            <Route
              path="drivers/:id"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <DriverDetail />
                </Suspense>
              }
            />
            <Route
              path="constructors"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <EntityLibrary kind="constructors" title="Constructors" eyebrow="TEAM LIBRARY" />
                </Suspense>
              }
            />
            <Route
              path="constructors/:id"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <ConstructorDetail />
                </Suspense>
              }
            />
            <Route
              path="circuits"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CircuitLibrary />
                </Suspense>
              }
            />
            <Route
              path="circuits/:id"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CircuitDetail />
                </Suspense>
              }
            />
            <Route
              path="races"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <RaceIndex />
                </Suspense>
              }
            />
            <Route
              path="races/:id"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <RaceDetail />
                </Suspense>
              }
            />
            <Route
              path="seasons"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <SeasonIndex />
                </Suspense>
              }
            />
            <Route
              path="seasons/:season"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <SeasonDetail />
                </Suspense>
              }
            />
            <Route
              path="compare"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Compare />
                </Suspense>
              }
            />
            <Route
              path="records"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Records />
                </Suspense>
              }
            />
            <Route
              path="cars"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CarLibrary />
                </Suspense>
              }
            />
            <Route
              path="search"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Search />
                </Suspense>
              }
            />
            <Route
              path="dataset"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Dataset />
                </Suspense>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </DatasetProvider>
    </BrowserRouter>
  );
}
