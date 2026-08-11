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
  constructor_name: string;
}

export interface DriverContribution extends Stats {
  driver_id: number;
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
  driver_name: string;
  constructor_id: number;
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
  winner_driver: string | null;
  winner_constructor_id: number | null;
  winner_constructor: string | null;
}

export interface RaceResult {
  position: number;
  driver_id: number;
  driver_name: string;
  constructor_id: number;
  constructor_name: string;
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
  winner_driver: string | null;
  winner_constructor_id: number | null;
  winner_constructor: string | null;
}

export interface SeasonRounds {
  season: number;
  rounds: SeasonRound[];
}

export interface RaceDetail extends Race {
  results: RaceResult[];
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

export interface SeasonSummary {
  season: number;
  races: number;
  entries: number;
  /** Always "wins". These are NOT championship standings -- no points column exists. */
  ranking_basis: string;
  drivers: NamedStats[];
  constructors: NamedStats[];
  races_list: Race[];
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
  kind: "driver" | "constructor" | "circuit" | "season";
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
  teammate_name: string;
  constructor_id: number;
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
