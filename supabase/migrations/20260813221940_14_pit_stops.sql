-- ============================================================================
-- Pit stops.
--
-- COVERAGE STARTS IN 2011. Seasons 2000-2010 return zero rows from the source
-- -- a real absence in the historical record, not a load failure. No row is
-- invented for them, and the coverage matrix names the window rather than
-- implying the whole dataset is covered.
--
-- 12,192 stops across 310 races. `duration` is NULL for 14 of them: the source
-- records the stop but not how long it took. NULL, never 0 -- a zero-second
-- pit stop is not a thing, and storing one would corrupt every average.
--
-- Durations are kept as the source's own strings ("22.213", and occasionally
-- "1:04.291" for a long stop). Parsing to an interval is a transformation a
-- consumer can do explicitly; doing it here would silently discard the
-- original text that can be checked against the source.
-- ============================================================================

create table pit_stops (
    id         bigint generated always as identity primary key,
    race_id    bigint not null references races(id) on delete cascade,
    driver_id  bigint not null references drivers(id),
    -- Lap the stop was made on, and which stop of the race it was for that
    -- driver (1 = first stop).
    lap        int    not null check (lap >= 1),
    stop       int    not null check (stop >= 1),
    -- Local time of day, as recorded. Not a timestamp: no date or zone is
    -- supplied, and inventing one would be a fabrication.
    time_of_day text,
    duration    text,
    dataset_id bigint references datasets(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    -- A driver makes at most one Nth stop per race.
    unique (race_id, driver_id, stop)
);

comment on table pit_stops is
    'Pit stops, 2011-2025 only. The source has none before 2011; absent rows '
    'mean no data exists, not that no stops were made.';
comment on column pit_stops.duration is
    'Stationary time as the source wrote it ("22.213", sometimes "1:04.291"). '
    'NULL for 14 stops where the source records the stop but not its length -- '
    'never 0, which would corrupt every average.';
comment on column pit_stops.time_of_day is
    'Local clock time as recorded. Deliberately not a timestamp: the source '
    'supplies no date or timezone.';

create index idx_pitstops_race on pit_stops(race_id);
create index idx_pitstops_driver on pit_stops(driver_id);
create index idx_pitstops_lap on pit_stops(race_id, lap);

alter table pit_stops enable row level security;
create policy public_read_pit_stops on pit_stops
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on pit_stops from anon, authenticated;

create trigger trg_pit_stops_updated_at before update on public.pit_stops
    for each row execute function public.set_updated_at();