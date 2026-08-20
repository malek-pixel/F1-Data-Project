import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { Stagger, staggerItem } from "../components/motion";
import { SearchField } from "../components/SearchField";
import { carPhoto } from "../components/carPhoto";
import { teamLogo } from "../components/teamLogo";
import { Async } from "../components/States";
import { dec, num } from "../components/format";
import { Badge, FilterChip, PageHeader, Panel, PaneHead, Segmented } from "../components/ui";
import { useApi, useDebounced } from "../hooks/useApi";
import { useCoverage } from "../hooks/useDataset";
import type { CarLibraryPayload, CarSeason, CarTeam } from "../types";

/**
 * Car Library (mockup § 08).
 *
 * The mockup's unit is a chassis -- MCL39, MP4/4 -- grouped by team and split
 * into current / recent / retired. The source has no chassis column, so the
 * unit here is the constructor-season: the car a team ran in a given year,
 * named by team and year instead of by a designation the dataset does not
 * carry. Every number on a card is measured. The chassis code is the one
 * thing shown as absent, because filling it in from memory would put
 * unsourced data behind a page that claims to be dataset-backed.
 */

const ERAS = [
  { id: "all", label: "All" },
  { id: "current", label: "Current" },
  { id: "recent", label: "Recent" },
  { id: "retired", label: "Retired" },
] as const;

type Era = (typeof ERAS)[number]["id"];

const ERA_TONE: Record<CarSeason["era"], "info" | "warning" | undefined> = {
  current: "info",
  recent: undefined,
  retired: undefined,
};

function CarCard({ car, team }: { car: CarSeason; team: string }) {
  const photo = carPhoto(team, car.season);
  return (
    <motion.div className="car-card" variants={staggerItem}>
      {/* The mockup shows a photo of each car, and every constructor-season
          has one. The frame is the fallback for a season a later ETL run
          adds: reusing an adjacent year would show the wrong livery. */}
      {photo ? (
        <div className="gallery__media gallery__media--car">
          <img src={photo} alt={`${team} ${car.season} car`} loading="lazy" decoding="async" width={800} height={600} />
        </div>
      ) : (
        <div className="gallery__media mono">
          CAR IMAGE
          <span>to be added</span>
        </div>
      )}
      <div className="car-card__head">
        <div>
          <div className="car-card__name">
            {team} <span className="mono">{car.season}</span>
          </div>
          <div className="mono car-card__chassis" title="No chassis designation in any source this project ingests">
            CHASSIS — to be added
          </div>
        </div>
        <Badge tone={ERA_TONE[car.era]}>{car.era.toUpperCase()}</Badge>
      </div>
      <div className="gallery__stats mono">
        <span>
          W <strong>{num(car.wins)}</strong>
        </span>
        <span>
          P <strong>{num(car.podiums)}</strong>
        </span>
        <span>
          R <strong>{num(car.races)}</strong>
        </span>
        <span>
          BEST <strong>P{num(car.best_finish)}</strong>
        </span>
        <span>
          AVG <strong>{dec(car.avg_classified_position)}</strong>
        </span>
      </div>
      <div className="mono car-card__drivers">{car.drivers.join(" · ")}</div>
    </motion.div>
  );
}

/**
 * One team's cars (mockup § 07).
 *
 * Current and recent cars are open; the retired archive stays behind a button
 * as the design shows -- a team with 26 seasons would otherwise bury every
 * other team below it.
 */
function TeamGallery({ team }: { team: CarTeam }) {
  const [showRetired, setShowRetired] = useState(false);
  const open = team.cars.filter((car) => car.era !== "retired");
  const retired = team.cars.filter((car) => car.era === "retired");
  const visible = showRetired ? team.cars : open.length ? open : retired.slice(0, 4);
  const hidden = team.cars.length - visible.length;

  return (
    <Panel>
      <PaneHead
        title={
          <span className="pane__title-row">
            {teamLogo(team.constructor_name) && (
              <img className="pane__logo" src={teamLogo(team.constructor_name)!} alt="" loading="lazy" decoding="async" width={34} height={20} />
            )}
            <Link to={`/constructors/${team.constructor_id}`}>{team.constructor_name}</Link>
          </span>
        }
        meta={`${team.first_season}–${team.last_season} · ${team.seasons} SEASONS · ${team.wins} WINS`}
      />
      <Stagger className="car-grid">
        {visible.map((car) => (
          <CarCard key={car.season} car={car} team={team.constructor_name} />
        ))}
      </Stagger>
      {hidden > 0 && (
        <div className="car-more">
          <button className="btn" onClick={() => setShowRetired(true)}>
            Show {hidden} retired →
          </button>
        </div>
      )}
    </Panel>
  );
}

export function CarLibrary() {
  const coverage = useCoverage();
  // A team page links here with ?team=, so the gallery opens pre-filtered.
  const [params] = useSearchParams();
  const [search, setSearch] = useState(params.get("team") ?? "");
  const [era, setEra] = useState<Era>("all");
  const debounced = useDebounced(search);
  const state = useApi<CarLibraryPayload>("/cars");

  return (
    <>
      <PageHeader
        eyebrow="LIBRARIES"
        title="Cars"
        sub={`One entry per constructor-season, ${coverage}. Chassis designations are not in the source; every other figure is measured from it.`}
      />

      <p style={{ fontSize: 13, color: "var(--text-dim)", maxWidth: "80ch" }}>
        <Badge tone="warning">Unit</Badge> A car here is the machine a team ran in a given season. The dataset
        records race classifications, not chassis: adding a chassis table keyed on constructor and season would fill
        in the designations without reshaping anything below. “Retired” describes the car, not the team.
      </p>

      <div className="controls">
        <SearchField
          id="car-search"
          label="SEARCH"
          className="searchfield--wide"
          placeholder="Team name…"
          value={search}
          loading={state.loading}
          onChange={setSearch}
        />
        <div className="field">
          <label htmlFor="car-era">ERA</label>
          <Segmented
            label="Era"
            active={era}
            onChange={setEra}
            options={ERAS.map((e) => ({ id: e.id, label: e.label }))}
          />
        </div>
      </div>

      <Async state={state} loadingRows={8}>
        {(payload) => {
          const teams = payload.teams
            .filter((team) => team.constructor_name.toLowerCase().includes(debounced.trim().toLowerCase()))
            .map((team) => ({
              ...team,
              cars: era === "all" ? team.cars : team.cars.filter((car) => car.era === era),
            }))
            .filter((team) => team.cars.length > 0);
          const shown = teams.reduce((sum, team) => sum + team.cars.length, 0);

          if (teams.length === 0) {
            return (
              <p className="table-empty">
                No teams match {debounced ? `“${debounced}”` : "this filter"}
                {era !== "all" ? ` in the ${era} era` : ""}.
              </p>
            );
          }

          return (
            <>
              {(debounced || era !== "all") && (
                <div className="filter-row">
                  <span className="mono filter-row__label">ACTIVE</span>
                  {debounced && <FilterChip label={`team: ${debounced}`} onClear={() => setSearch("")} />}
                  {era !== "all" && <FilterChip label={`era: ${era}`} onClear={() => setEra("all")} />}
                </div>
              )}
              <p className="mono" style={{ fontSize: 12, color: "var(--text-faint)" }}>
                {shown} CONSTRUCTOR-SEASONS · {teams.length} TEAMS · {coverage}
              </p>
              {teams.map((team) => (
                <TeamGallery key={team.constructor_id} team={team} />
              ))}
              <p style={{ fontSize: 12, color: "var(--text-faint)", marginTop: 24, maxWidth: "72ch" }}>
                Poles, fastest laps, points and reliability are absent from the source and are not shown. Best is the
                best classified position that season; avg includes retirements, which the source does not flag.
              </p>
            </>
          );
        }}
      </Async>
    </>
  );
}
