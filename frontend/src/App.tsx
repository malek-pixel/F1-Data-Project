import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { DatasetProvider } from "./hooks/useDataset";
import { EmptyState } from "./components/States";
import { PageHeader } from "./components/ui";
import { RaceDetail, RaceIndex, SeasonDetail, SeasonIndex } from "./pages/Calendar";
import { CircuitDetail, CircuitLibrary } from "./pages/Circuits";
import { Compare } from "./pages/Compare";
import { ConstructorDetail } from "./pages/ConstructorDetail";
import { CarLibrary, Dataset, Insights, Records } from "./pages/Data";
import { DriverDetail } from "./pages/DriverDetail";
import { EntityLibrary } from "./pages/EntityLibrary";
import { Home } from "./pages/Home";
import { Methodology } from "./pages/Methodology";

function NotFound() {
  return (
    <>
      <PageHeader eyebrow="404" title="Page not found" />
      <EmptyState title="Nothing here" body="That route does not exist. Use the navigation or press ⌘K to search." />
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <DatasetProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route
            path="drivers"
            element={<EntityLibrary kind="drivers" title="Drivers" eyebrow="DRIVER LIBRARY" />}
          />
          <Route path="drivers/:id" element={<DriverDetail />} />
          <Route
            path="constructors"
            element={<EntityLibrary kind="constructors" title="Constructors" eyebrow="TEAM LIBRARY" />}
          />
          <Route path="constructors/:id" element={<ConstructorDetail />} />
          <Route path="circuits" element={<CircuitLibrary />} />
          <Route path="circuits/:id" element={<CircuitDetail />} />
          <Route path="races" element={<RaceIndex />} />
          <Route path="races/:id" element={<RaceDetail />} />
          <Route path="seasons" element={<SeasonIndex />} />
          <Route path="seasons/:season" element={<SeasonDetail />} />
          <Route path="compare" element={<Compare />} />
          <Route path="insights" element={<Insights />} />
          <Route path="records" element={<Records />} />
          <Route path="cars" element={<CarLibrary />} />
          <Route path="dataset" element={<Dataset />} />
          <Route path="methodology" element={<Methodology />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      </DatasetProvider>
    </BrowserRouter>
  );
}
