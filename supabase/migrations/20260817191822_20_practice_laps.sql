-- ============================================================================
-- Practice timing: a SECOND SOURCE, deliberately kept apart.
--
-- Every other table here derives from Jolpica. This one comes from FastF1,
-- which reads Formula 1's own live-timing service -- the only source that
-- carries practice laps, tyre compounds and sector times. Jolpica publishes
-- none of them.
--
-- It is a separate table rather than extra columns on lap_times, because
-- blending two providers into one table is how they begin disagreeing with no
-- way left to tell which one is wrong. Coverage differs too: live timing
-- starts in 2018, and race lap timings go back to 2000.
--
-- DELETED LAPS ARE STORED AND FLAGGED, NOT DROPPED. Their times were struck
-- off, usually for track limits, but the lap happened -- and which laps stood
-- is exactly what decides a session's fastest time. A consumer excludes them
-- deliberately; it cannot recover them if ingestion threw them away.
--
-- Times are seconds, and NULL where the source timed nothing (an out-lap, a
-- lap not completed). Never 0, which would be the fastest lap ever set.
-- ============================================================================

create table practice_laps (
    id         bigint generated always as identity primary key,
    race_id    bigint not null references races(id) on delete cascade,
    driver_id  bigint not null references drivers(id),
    session    text   not null check (session in ('fp1','fp2','fp3')),
    lap        int    check (lap >= 1),
    stint      int    check (stint >= 1),
    lap_time   numeric(9,3) check (lap_time > 0),
    sector1    numeric(9,3) check (sector1 > 0),
    sector2    numeric(9,3) check (sector2 > 0),
    sector3    numeric(9,3) check (sector3 > 0),
    -- SOFT | MEDIUM | HARD | INTERMEDIATE | WET | UNKNOWN, verbatim from the
    -- source. 'UNKNOWN' is kept rather than folded into NULL: the source gave
    -- an answer, and the answer was that it did not know. That is a different
    -- statement from having no value at all.
    compound   text,
    tyre_life  int    check (tyre_life >= 0),
    fresh_tyre boolean,
    speed_trap numeric(7,2) check (speed_trap > 0),
    is_personal_best boolean,
    deleted    boolean not null default false,
    dataset_id bigint references datasets(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (race_id, driver_id, session, lap)
);

comment on table practice_laps is
    'Practice-session timing from FastF1 / F1 live timing, 2018 onward. A '
    'different provider from every other table here; never blend the two.';
comment on column practice_laps.deleted is
    'Lap time was struck off. Kept and flagged, never dropped: which laps '
    'stood is what decides a session fastest time.';
comment on column practice_laps.compound is
    'Verbatim source value. UNKNOWN means the source recorded that it did not '
    'know, which is not the same as NULL.';

create index idx_practice_race    on practice_laps(race_id, session);
create index idx_practice_driver  on practice_laps(driver_id);
create index idx_practice_fastest on practice_laps(race_id, session, lap_time);

alter table practice_laps enable row level security;
create policy public_read_practice_laps on practice_laps
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on practice_laps from anon, authenticated;

create trigger trg_practice_laps_updated_at before update on public.practice_laps
    for each row execute function public.set_updated_at();


-- Session classification: each driver's best lap that STOOD.
--
-- Derived, never stored, so it cannot drift from the laps beneath it. No
-- source publishes a practice classification; ordering by quickest valid lap
-- is how one is formed.
create or replace view v_practice_results as
    select p.race_id,
           p.session,
           d.id   as driver_id,
           d.slug as driver_slug,
           d.display_name as driver_name,
           min(p.lap_time) filter (where not p.deleted) as best_lap,
           count(*) as laps,
           count(*) filter (where p.deleted) as deleted_laps
      from practice_laps p
      join drivers d on d.id = p.driver_id
     group by p.race_id, p.session, d.id, d.slug, d.display_name;

grant select on v_practice_results to anon, authenticated;
