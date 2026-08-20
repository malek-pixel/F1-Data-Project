-- ============================================================================
-- Staging + ingestion
--
-- Raw CSV lands in staging as text, is validated there, and only then is
-- normalised into the production tables. Malformed source data therefore
-- cannot reach a table with foreign keys and check constraints.
--
-- Every promotion step is an UPSERT keyed on a natural unique constraint, so
-- re-running the whole import is idempotent -- it updates, never duplicates.
-- ============================================================================

create table staging_results (
    id             bigint generated always as identity primary key,
    run_id         uuid not null,
    line_no        int  not null,
    -- Deliberately all text: staging accepts whatever the file contains so
    -- that type failures are *reported* rather than aborting the load.
    season         text,
    round          text,
    race_name      text,
    race_date      text,
    position       text,
    driver         text,
    constructor    text,
    -- Resolved during validation, before promotion.
    circuit_key    text,
    is_valid       boolean not null default false,
    rejection      text,
    loaded_at      timestamptz not null default now()
);
create index idx_staging_run on staging_results(run_id, is_valid);

alter table staging_results enable row level security;
-- No policies at all: staging is server-side only and must never be readable
-- by the browser, valid or not.

-- Curated race_name -> circuit resolution. The source has no circuit column
-- and race_name is not a stable key: the European, German, French, Japanese
-- and United States Grands Prix all changed venue inside 2000-2025.
create table circuit_map (
    id           bigint generated always as identity primary key,
    race_name    text not null,
    season_from  int  not null,
    season_to    int  not null,
    circuit_key  text not null,
    circuit_name text not null,
    country      text not null,
    check (season_to >= season_from),
    unique (race_name, season_from)
);
comment on table circuit_map is
    'Encodes external F1 knowledge, not source data. Auditable as rows; must '
    'be reviewed when a new season is added. The import FAILS on any '
    '(race_name, season) with no matching rule rather than dropping the race.';

alter table circuit_map enable row level security;
create policy public_read_circuit_map on circuit_map
    for select to anon, authenticated using (true);

revoke insert, update, delete, truncate on staging_results, circuit_map from anon, authenticated;
