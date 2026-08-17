/** Mirrors backend/app/schemas.py. */

export interface Stats {
  entries: number;
  wins: number;
  podiums: number;
  top5: number;
  top10: number;
  /** null when there are no entries -- distinct from 0. */
  win_rate: number | null;
  podium_rate: number | null;
  top5_rate: number | null;
  top10_rate: number | null;
  /** Mean final classification incl. retirements. NOT average finishing position. */
  avg_classified_position: number | null;
  best_classified_position: number | null;
  /** false below the backend's minimum entry count; show the value, flag it. */
  rates_reliable: boolean;

  /*
   * Enrichment-derived (finishing status, points, grid). All nullable: a build
   * without data/jolpica_results.csv has none of them, and null must read as
   * "not known", never as zero.
   */
  /** Classified finishes. NOT the same as "saw the flag" -- a lapped car is classified. */
  finishes: number | null;
  dnfs: number | null;
  /** Over rows that HAVE a finishing status, not over all entries. */
  dnf_rate: number | null;
  /** Championship points as awarded, halves included. */
  points: number | null;
  /** Excludes pit-lane starts (grid 0), which are real but not a grid slot. */
  avg_grid: number | null;
  /** Grid minus finish, classified finishes only. Positive = places gained. */
  avg_positions_gained: number | null;
}

export interface NamedStats extends Stats {
  id: number;
  name: string;
}

export interface SeasonStats extends Stats {
  season: number;
}

export interface ConstructorSpell extends SeasonStats {
  constructor_id: number;
  constructor_slug: string;
  constructor_name: string;
}

export interface DriverContribution extends Stats {
  driver_id: number;
  driver_slug: string;
  driver_name: string;
  entry_share: number | null;
  win_share: number | null;
  podium_share: number | null;
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface Circuit {
  id: number;
  slug: string;
  name: string;
  country: string;
  has_map: boolean;
  races: number;
  top_winner: string | null;
  top_winner_wins: number | null;
}

export interface CircuitDetail extends Circuit {
  stats: Stats;
  winners: CircuitWinner[];
  top_drivers: NamedStats[];
  top_constructors: NamedStats[];
}

export interface CircuitWinner {
  season: number;
  race_id: number;
  race_name: string;
  driver_id: number;
  driver_slug: string;
  driver_name: string;
  constructor_id: number;
  constructor_slug: string;
  constructor_name: string;
}

export interface Race {
  id: number;
  season: number;
  round: number;
  name: string;
  date: string;
  circuit_id: number;
  circuit_name: string;
  circuit_slug: string;
  /** Null when the source carries no position-1 row for this race. */
  winner_driver_id: number | null;
  /** Portable identifier. Link on this, not on the numeric id: ids are
   *  assigned per data store, so the same number means a different driver
   *  depending on which backend served the request. Null together with the
   *  id -- both come from the same optional join. */
  winner_driver_slug: string | null;
  winner_driver: string | null;
  winner_constructor_id: number | null;
  winner_constructor_slug: string | null;
  winner_constructor: string | null;
}

export interface RaceResult {
  position: number;
  driver_id: number;
  driver_slug: string;
  driver_name: string;
  constructor_id: number;
  constructor_slug: string;
  constructor_name: string;
  /** Null means not known for this row, never zero. `grid: 0` is a real
   *  value -- a pit-lane start. */
  grid: number | null;
  laps: number | null;
  points: number | null;
  /** Raw source text ("Finished", "+1 Lap", "Gearbox"). Deliberately not
   *  bucketed into an enum: the detail is the value. */
  status: string | null;
  classification: string | null;
  position_text: string | null;
}

/** One round of a season with its winner. Winner fields are null when the
 *  source carries no position-1 row for that race. */
export interface SeasonRound {
  race_id: number;
  round: number;
  race_name: string;
  date: string;
  circuit_name: string;
  circuit_slug: string;
  winner_driver_id: number | null;
  winner_driver_slug: string | null;
  winner_driver: string | null;
  winner_constructor_id: number | null;
  winner_constructor_slug: string | null;
  winner_constructor: string | null;
}

export interface SeasonRounds {
  season: number;
  rounds: SeasonRound[];
}

/** Qualifying classification for one race. */
export interface QualifyingResult {
  position: number;
  q1: string | null;
  q2: string | null;
  q3: string | null;
  driver_id: number;
  driver_name: string;
  constructor_id: number;
  constructor_name: string;
  /** The grid actually started from -- differs after penalties. */
  race_grid: number | null;
}

export interface SprintResult {
  position: number;
  classification: string | null;
  status: string | null;
  points: number | null;
  grid: number | null;
  laps: number | null;
  driver_id: number;
  driver_name: string;
  constructor_id: number;
  constructor_name: string;
}

export interface PitStop {
  lap: number;
  stop: number;
  /** Raw source string, e.g. "22.213". Null where unrecorded -- never 0. */
  duration: string | null;
  time_of_day: string | null;
  driver_id: number;
  driver_name: string;
}

/**
 * A session block that knows WHY it is empty.
 *
 * An empty array alone cannot distinguish "no qualifying was recorded for this
 * race" from "nobody qualified", and only one of those is ever true.
 */
export interface SessionBlock<T> {
  available: boolean;
  unavailable_reason: string | null;
  items: T[];
}

export interface RaceDetail extends Race {
  results: RaceResult[];
  qualifying: SessionBlock<QualifyingResult>;
  sprint: SessionBlock<SprintResult>;
  pit_stops: SessionBlock<PitStop>;
  fastest_lap: FastestLapSection;
}

export interface DriverDetail {
  id: number;
  name: string;
  stats: Stats;
  constructors: ConstructorSpell[];
}

export interface ConstructorDetail {
  id: number;
  name: string;
  stats: Stats;
  seasons: SeasonStats[];
}

/** One row of a championship table: points, from race + sprint results. */
export interface StandingsRow {
  position: number;
  id: number;
  /** Portable identifier -- link on this, not on `id`. */
  slug: string;
  name: string;
  points: number | null;
  wins: number;
  podiums: number;
  entries: number;
}

export interface Standings {
  drivers: StandingsRow[];
  constructors: StandingsRow[];
  /** "points". */
  basis: string;
  includes_sprint_points: boolean;
  /** Tie-break caveat -- the official countback rule is not implemented. */
  caveat: string;
}

export interface SeasonSummary {
  season: number;
  races: number;
  entries: number;
  /**
   * Describes `drivers`/`constructors` below -- always "wins".
   *
   * It does NOT describe `standings`, which is the real championship. This
   * field previously said no points column existed; that stopped being true
   * when points were ingested.
   */
  ranking_basis: string;
  drivers: NamedStats[];
  constructors: NamedStats[];
  races_list: Race[];
  /** The actual championship: race + sprint points. */
  standings: Standings;
}

export interface SeasonIndexRow {
  season: number;
  races: number;
  entries: number;
  drivers: number;
  constructors: number;
}

export interface Comparison {
  left: Stats;
  right: Stats;
  left_name: string;
  right_name: string;
  shared_seasons: number[];
  comparable: boolean;
  left_shared?: Stats;
  right_shared?: Stats;
  methodology: string;
}

export interface RecordEntry {
  record: string;
  entity: string;
  value: number;
  context?: string;
  methodology: string;
}

export interface Insight {
  kind: string;
  headline: string;
  detail: string;
  basis: string;
}

export interface DatasetSummary {
  source: string;
  season_from: number;
  season_to: number;
  tables: { name: string; rows: number; columns: { name: string; type: string; nullable: boolean }[] }[];
  available_fields: string[];
  unavailable_fields: string[];
  known_issues: string[];
}

export interface SearchHit {
  kind: "driver" | "constructor" | "circuit" | "race" | "season";
  id: number;
  label: string;
  sublabel: string;
}

export interface Health {
  status: string;
  season_from: number;
  season_to: number;
  seasons: number;
  races: number;
  results: number;
  drivers: number;
  constructors: number;
  circuits: number;
  circuits_with_map: number;
  /** Permanently false. This is a static historical dataset. */
  live_data: boolean;
}

// ---------------------------------------------------------------- advanced

/** Registry entry: the published definition of one metric. */
export interface MetricDoc {
  key: string;
  name: string;
  formula: string;
  columns: string[];
  level: string;
  definition: string;
  edge_cases: string;
  limitations: string;
  min_sample: number | null;
}

export interface Distribution {
  entries: number;
  median: number | null;
  stdev: number | null;
  spread_reliable: boolean;
  iqr: number | null;
  worst: number | null;
  histogram: { bucket: string; count: number; share: number }[];
}

export interface TeammateSpell {
  teammate_id: number;
  teammate_slug: string;
  teammate_name: string;
  constructor_id: number;
  constructor_slug: string;
  constructor_name: string;
  seasons: number[];
  shared_races: number;
  ahead: number;
  behind: number;
  h2h_rate: number;
  /** Positive = this driver was classified ahead on average. */
  avg_position_delta: number;
  my_avg_position: number;
  teammate_avg_position: number;
  comparable: boolean;
}

export interface TeammateSummary {
  shared_races: number;
  ahead: number;
  behind: number;
  h2h_rate: number | null;
  avg_position_delta: number | null;
  teammates: number;
  excluded_short_spells: number;
}

export interface TeammateResponse {
  summary: TeammateSummary;
  spells: TeammateSpell[];
  methodology: MetricDoc;
}

export interface CircuitRecord {
  circuit_id: number;
  circuit_name: string;
  slug: string;
  appearances: number;
  wins: number;
  podiums: number;
  avg_classified_position: number;
  best_classified_position: number;
  /** Positive = better here than the driver's career norm. */
  delta_vs_career: number;
  meets_threshold: boolean;
}

export interface DriverCircuitsResponse {
  circuits: CircuitRecord[];
  min_appearances: number;
  methodology: MetricDoc;
}

export interface SeasonRow {
  season: number;
  races: number;
  driver_winners: number;
  constructor_winners: number;
  top_driver_win_share: number;
  top_constructor_win_share: number;
}

/** One constructor-season: the car a team ran that year (see /cars). */
export interface CarSeason {
  season: number;
  races: number;
  entries: number;
  wins: number;
  podiums: number;
  best_finish: number;
  avg_classified_position: number;
  drivers: string[];
  era: "current" | "recent" | "retired";
}

export interface CarTeam {
  constructor_id: number;
  constructor_name: string;
  seasons: number;
  wins: number;
  first_season: number;
  last_season: number;
  cars: CarSeason[];
}

export interface CarLibraryPayload {
  teams: CarTeam[];
  unit: string;
  chassis_available: boolean;
}

export interface Era {
  decade: number;
  label: string;
  seasons: number;
  races: number;
  drivers: number;
  constructors: number;
  largest_field: number;
  top_winners: { name: string; wins: number }[];
}


/** The quickest lap driven in a race, derived from the lap timings.
 *
 *  NOT the official fastest-lap award: no source publishes who received it,
 *  and since 2019 it carries eligibility rules (a classified finish, and a
 *  top-ten position for the point) that a raw minimum does not apply. The two
 *  can disagree, so they are never labelled the same.
 *
 *  `available: false` means lap timings have not been ingested for that race
 *  — the fetch is per race and resumable — never that nobody set a lap. */
export interface FastestLap {
  lap: number;
  time_text: string;
  time_ms: number;
  driver_id: number;
  driver_slug: string;
  driver_name: string;
}

export interface FastestLapSection {
  available: boolean;
  unavailable_reason: string | null;
  basis: string;
  item: FastestLap | null;
}
