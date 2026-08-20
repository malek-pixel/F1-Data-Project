-- ============================================================================
-- F1 Data Project -- core relational schema
--
-- DESIGN RULE (documented in docs/data-model.md):
--   Dimension tables carry descriptive columns a named future source would
--   fill; those stay NULL and NULL means "not yet known".
--   The results fact table carries ONLY measured columns that exist in the
--   source. Columns such as points/grid/laps/status are deliberately absent
--   rather than present-and-always-NULL, because an all-NULL column across
--   10,550 rows invites zero-substitution and breaks every aggregate.
--   Adding them is a single migration once a source provides them.
-- ============================================================================

-- ---------------------------------------------------------------- provenance

create table data_sources (
    id            bigint generated always as identity primary key,
    source_key    text        not null unique,
    name          text        not null,
    source_type   text        not null check (source_type in ('csv','api','manual','derived')),
    source_url    text,
    license_notes text,
    description   text,
    created_at    timestamptz not null default now()
);
comment on table data_sources is
    'Where data came from. Never populated with invented attribution.';

create table datasets (
    id             bigint generated always as identity primary key,
    source_id      bigint      not null references data_sources(id),
    dataset_key    text        not null,
    version        text        not null,
    coverage_start int,
    coverage_end   int,
    row_count      int,
    checksum       text,
    status         text        not null default 'active'
                   check (status in ('active','superseded','failed')),
    description    text,
    imported_at    timestamptz not null default now(),
    unique (dataset_key, version)
);
comment on column datasets.checksum is
    'SHA-256 of the source file, so an import can prove which bytes it read.';

-- ---------------------------------------------------------------- dimensions

create table seasons (
    id           bigint generated always as identity primary key,
    year         int         not null unique check (year between 1950 and 2100),
    display_name text        not null,
    dataset_id   bigint      references datasets(id),
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);
-- Race count is deliberately NOT stored here: it is derivable from races and
-- storing it would create a value that can silently disagree with the rows.

create table circuits (
    id            bigint generated always as identity primary key,
    circuit_key   text        not null unique,
    circuit_name  text        not null,
    country       text        not null,
    -- Below: filled by a future circuits source (e.g. Ergast circuits.csv).
    -- NULL means not yet known. Never estimated.
    official_name text,
    locality      text,
    latitude      numeric(9,6) check (latitude between -90 and 90),
    longitude     numeric(9,6) check (longitude between -180 and 180),
    source_url    text,
    -- Track map asset shipped with the frontend; NULL when none exists.
    svg_asset     text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);
comment on column circuits.circuit_key is
    'Stable slug. Derived from a curated race_name -> circuit map, because the '
    'source CSV has no circuit column and race names moved venue over time.';

create table drivers (
    id               bigint generated always as identity primary key,
    driver_key       text        not null unique,
    display_name     text        not null,
    -- Filled by a future drivers source. first/last are NOT derived by
    -- splitting display_name -- "Juan Pablo Montoya" cannot be split reliably.
    first_name       text,
    last_name        text,
    abbreviation     text check (abbreviation ~ '^[A-Z]{3}$'),
    nationality      text,
    date_of_birth    date check (date_of_birth > '1900-01-01'),
    permanent_number int check (permanent_number between 1 and 99),
    source_url       text,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create table constructors (
    id               bigint generated always as identity primary key,
    constructor_key  text        not null unique,
    constructor_name text        not null,
    nationality      text,
    source_url       text,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
comment on table constructors is
    'Historically distinct constructors are separate rows and are never merged '
    'without evidence: Sauber, BMW Sauber and Alfa Romeo are three entities.';

-- ---------------------------------------------------------------------- cars
-- Created because the product has a Car Library. Intentionally EMPTY: the
-- source has no car data, and inventing chassis or engine values is forbidden.
create table cars (
    id                  bigint generated always as identity primary key,
    constructor_id      bigint      not null references constructors(id),
    season_id           bigint      not null references seasons(id),
    car_name            text        not null,
    chassis_name        text,
    engine_manufacturer text,
    engine_name         text,
    source_id           bigint      references data_sources(id),
    source_url          text,
    -- Genuinely open-ended verified attributes only; never performance guesses.
    metadata            jsonb       not null default '{}'::jsonb,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    unique (constructor_id, season_id, car_name)
);

-- --------------------------------------------------------------------- races

create table races (
    id            bigint generated always as identity primary key,
    season_id     bigint      not null references seasons(id),
    round         int         not null check (round >= 1),
    race_name     text        not null,
    official_name text,
    circuit_id    bigint      not null references circuits(id),
    race_date     date        not null,
    source_url    text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (season_id, round)
);

-- ------------------------------------------------------------------- results
-- The core fact table.
create table results (
    id             bigint generated always as identity primary key,
    race_id        bigint not null references races(id) on delete cascade,
    driver_id      bigint not null references drivers(id),
    constructor_id bigint not null references constructors(id),
    -- Car is nullable and unpopulated: the source cannot identify which car
    -- produced a result. The relationship exists for future ingestion.
    car_id         bigint references cars(id),
    -- FINAL CLASSIFICATION ORDER, 1..N. NOT a finishing status: the source has
    -- no status column, so retirements are ranked here alongside finishers.
    -- Every metric derived from this is named "classified", not "finishing".
    position       int not null check (position between 1 and 40),
    dataset_id     bigint references datasets(id),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    -- Verified against the source before enforcing: 0 duplicates across all
    -- 10,550 rows. One driver has exactly one classification per race.
    unique (race_id, driver_id)
);
comment on column results.position is
    'Classification order, not finishing status. No DNF/DNS/DSQ column exists '
    'in the source, so a lap-1 retirement still carries a position number.';

-- ------------------------------------------------ driver/constructor seasons
-- Season-aware relationship. Teammate analysis must never be inferred from
-- arbitrary career overlap -- it requires a shared constructor in a shared
-- race, which this table plus results makes explicit.
create table driver_constructor_seasons (
    id             bigint generated always as identity primary key,
    driver_id      bigint not null references drivers(id),
    constructor_id bigint not null references constructors(id),
    season_id      bigint not null references seasons(id),
    race_count     int    not null check (race_count > 0),
    first_round    int    not null check (first_round >= 1),
    last_round     int    not null check (last_round >= 1),
    created_at     timestamptz not null default now(),
    unique (driver_id, constructor_id, season_id),
    check (last_round >= first_round)
);
comment on table driver_constructor_seasons is
    'Derived from results, not hand-entered. A mid-season switch produces two '
    'rows for one driver in one season.';

-- ------------------------------------------------------------ data quality
create table data_quality_checks (
    id            bigint generated always as identity primary key,
    run_id        uuid        not null,
    check_name    text        not null,
    dataset_key   text,
    status        text        not null check (status in ('pass','warn','fail')),
    severity      text        not null check (severity in ('info','warning','fatal')),
    affected_rows int         not null default 0,
    details       text,
    executed_at   timestamptz not null default now()
);
create index idx_dq_run on data_quality_checks(run_id, executed_at desc);

-- --------------------------------------------------- metric definitions
-- The published methodology, stored so the frontend can explain any number
-- without the explanation drifting from the implementation.
create table metric_definitions (
    id                 bigint generated always as identity primary key,
    metric_key         text        not null,
    display_name       text        not null,
    definition         text        not null,
    formula            text        not null,
    source_fields      text[]      not null,
    aggregation_level  text        not null,
    edge_cases         text,
    limitations        text        not null,
    sample_requirement int,
    version            text        not null default '1.0',
    active             boolean     not null default true,
    created_at         timestamptz not null default now(),
    unique (metric_key, version)
);
comment on column metric_definitions.limitations is
    'NOT NULL on purpose: a metric published without stated limitations reads '
    'as more authoritative than it is.';

-- ------------------------------------------------------------------ indexes
-- Chosen from the application''s actual query patterns, not added blindly.
create index idx_results_race        on results(race_id);
create index idx_results_driver      on results(driver_id);
create index idx_results_constructor on results(constructor_id);
create index idx_results_position    on results(position) where position <= 10;
-- Teammate analysis self-joins on (race, constructor); this is the single
-- most expensive query in the product and was 75x slower without it.
create index idx_results_race_ctor   on results(race_id, constructor_id);
create index idx_races_season        on races(season_id);
create index idx_races_circuit       on races(circuit_id);
create index idx_races_date          on races(race_date);
create index idx_dcs_driver          on driver_constructor_seasons(driver_id);
create index idx_dcs_constructor     on driver_constructor_seasons(constructor_id);
create index idx_dcs_season          on driver_constructor_seasons(season_id);

-- Trigram indexes for substring search without scanning every row.
create extension if not exists pg_trgm;
create index idx_drivers_name_trgm      on drivers      using gin (display_name gin_trgm_ops);
create index idx_constructors_name_trgm on constructors using gin (constructor_name gin_trgm_ops);
create index idx_circuits_name_trgm     on circuits     using gin (circuit_name gin_trgm_ops);

-- ------------------------------------------------------- updated_at triggers
create or replace function set_updated_at() returns trigger
language plpgsql
-- search_path pinned: an unqualified reference in a SECURITY-sensitive
-- function must not resolve through a caller-controlled path.
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

do $$
declare t text;
begin
    foreach t in array array['seasons','circuits','drivers','constructors','cars','races','results']
    loop
        execute format(
            'create trigger trg_%1$s_updated_at before update on public.%1$s
             for each row execute function public.set_updated_at()', t);
    end loop;
end $$;
