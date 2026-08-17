-- ============================================================================
-- Lap timings and the race-weekend timetable.
--
-- LAP TIMES
-- ---------
-- One row per driver per lap. Roughly half a million rows across the covered
-- seasons, fetched a race at a time because the source caps a page at 100
-- rows server-side.
--
-- `time_ms` is derived from `time_text` by a single documented rule and is
-- what every query sorts on -- the raw string is text and sorts wrongly.
-- NULL means the string would not parse, and is a finding. It is never 0: a
-- zero lap time does not fail a query, it wins it, and would surface as the
-- fastest lap of its race.
--
-- There is deliberately no upper bound on time_ms. Red-flagged races record
-- the suspension inside the lap -- the 2023 Australian Grand Prix has 49 laps
-- over five minutes, the longest 33 minutes -- and a CHECK would reject
-- correct data.
--
-- SESSIONS
-- --------
-- The weekend TIMETABLE: when each session was scheduled. It is not practice
-- results, and there is deliberately no practice_results table, because the
-- source has no practice classifications at all (its /practice, /fp1 and
-- /sessions routes return 400 or 404). An empty table would read as "nobody
-- set a time" rather than "this was never available".
--
-- Coverage begins in 2006; earlier seasons carry a race date and nothing
-- else, which is a real gap in the source.
-- ============================================================================

create table lap_times (
    id         bigint generated always as identity primary key,
    race_id    bigint not null references races(id) on delete cascade,
    driver_id  bigint not null references drivers(id),
    lap        int    not null check (lap >= 1),
    -- Running order at the end of this lap, not the finishing position.
    position   int    check (position >= 1),
    time_text  text   not null,
    time_ms    int    check (time_ms > 0),
    dataset_id bigint references datasets(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, driver_id, lap)
);

comment on table lap_times is
    'Per-lap timings. Coverage is per race and may be partial: the ingestion '
    'is resumable, so absent races mean not yet fetched or no laps recorded, '
    'never zero laps run.';
comment on column lap_times.time_ms is
    'Lap time in milliseconds, derived from time_text. NULL when the source '
    'string would not parse -- never 0, which would win every fastest-lap '
    'query. Unbounded above: red-flagged laps include the suspension.';
comment on column lap_times.position is
    'Running order at the end of this lap. Not the finishing position.';

create index idx_lap_times_race    on lap_times(race_id);
create index idx_lap_times_driver  on lap_times(driver_id);
create index idx_lap_times_fastest on lap_times(race_id, time_ms);

alter table lap_times enable row level security;
create policy public_read_lap_times on lap_times
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on lap_times from anon, authenticated;

create trigger trg_lap_times_updated_at before update on public.lap_times
    for each row execute function public.set_updated_at();


create table sessions (
    id         bigint generated always as identity primary key,
    race_id    bigint not null references races(id) on delete cascade,
    session    text   not null check (session in
                   ('fp1','fp2','fp3','sprint_qualifying','sprint','qualifying')),
    date       date   not null,
    -- NULL for most pre-2018 weekends: the source records the day but not the
    -- clock time. Absent, not midnight.
    time       time,
    dataset_id bigint references datasets(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, session)
);

comment on table sessions is
    'Race-weekend timetable (2006-2025). Schedule only: no classifications, '
    'no lap times, no drivers. The source publishes no practice results, so '
    'having FP1 here says nothing about having its outcome.';
comment on column sessions.session is
    '2023 SprintShootout and 2024+ SprintQualifying are the same session '
    'renamed, stored under one code so callers need not know the season.';

create index idx_sessions_race on sessions(race_id);

alter table sessions enable row level security;
create policy public_read_sessions on sessions
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on sessions from anon, authenticated;

create trigger trg_sessions_updated_at before update on public.sessions
    for each row execute function public.set_updated_at();
