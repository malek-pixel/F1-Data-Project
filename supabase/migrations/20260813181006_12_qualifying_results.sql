-- ============================================================================
-- Qualifying.
--
-- A separate session from the race, so a separate table -- same reasoning as
-- sprint_results.
--
-- COVERAGE IS GENUINELY PARTIAL, and the schema must not pretend otherwise:
--
--     2000    88 / 373 rows   (24%)
--     2001    22 / 373 rows   ( 6%)
--     2002    42 / 359 rows   (12%)
--     2003+   complete, 99-100% every season
--
-- Those first three seasons are a real gap in the source, not a load failure.
-- A row simply does not exist where the source has nothing; no row is invented
-- to square the totals with `results`.
--
-- Q1/Q2/Q3 DID NOT ALWAYS EXIST. The three-segment format began in 2006.
-- Before that, qualifying ran one- or two-lap formats with a single time.
-- Those columns are therefore NULL for early seasons, meaning "this session
-- did not exist" -- never zero, and never the same time copied across three
-- columns to make the shape look uniform.
--
-- Times are stored as TEXT in the source's own "1:23.456" form. Parsing them
-- to an interval would be a silent transformation, and the raw string is what
-- can be checked against the source.
-- ============================================================================

create table qualifying_results (
    id             bigint generated always as identity primary key,
    race_id        bigint not null references races(id) on delete cascade,
    driver_id      bigint not null references drivers(id),
    constructor_id bigint not null references constructors(id),
    -- Qualifying classification. NOT the same as the race grid: penalties,
    -- gearbox changes and pit-lane starts move drivers afterwards. The grid
    -- actually started from is results.grid.
    position       int    not null check (position between 1 and 40),
    q1             text,
    q2             text,
    q3             text,
    dataset_id     bigint references datasets(id),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    unique (race_id, driver_id)
);

comment on table qualifying_results is
    'Qualifying, 2000-2025. Coverage is partial before 2003 (24%/6%/12%) and '
    'complete from 2003. Absent rows mean the source has no data, not that a '
    'driver did not qualify.';
comment on column qualifying_results.position is
    'Qualifying classification, NOT the starting grid. Penalties and pit-lane '
    'starts change the grid afterwards -- use results.grid for that.';
comment on column qualifying_results.q1 is
    'Raw source time, e.g. "1:23.456". NULL means the segment did not exist '
    '(pre-2006) or the driver set no time -- never zero.';

create index idx_qualifying_race on qualifying_results(race_id);
create index idx_qualifying_driver on qualifying_results(driver_id);
create index idx_qualifying_constructor on qualifying_results(constructor_id);
-- Pole positions are the most common lookup against this table.
create index idx_qualifying_pole on qualifying_results(race_id) where position = 1;

alter table qualifying_results enable row level security;
create policy public_read_qualifying_results on qualifying_results
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on qualifying_results from anon, authenticated;

create trigger trg_qualifying_results_updated_at before update on public.qualifying_results
    for each row execute function public.set_updated_at();