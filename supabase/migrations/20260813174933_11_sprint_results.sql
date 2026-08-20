-- ============================================================================
-- Sprint results.
--
-- A SEPARATE TABLE, not extra rows in `results`. A sprint is a distinct event
-- that happens to share a Grand Prix weekend: its own grid, its own
-- classification, its own (smaller) points scale. Folding it into `results`
-- would double every driver's apparent race count and corrupt every rate that
-- uses entries as a denominator.
--
-- Discovered by validation, not assumed: championship totals computed from
-- Grand Prix points alone matched the official standings exactly for
-- 2000-2020, then fell short from 2021 by 7 / 21 / 45 / 38 / 29 points --
-- precisely the sprint era. The gap was the missing dataset.
--
-- Sprints joined the calendar in 2021 and the format changed more than once
-- (sprint qualifying, sprint shootout). Only the RESULT is modelled here,
-- because only the result is what the source reliably provides.
-- ============================================================================

create table sprint_results (
    id             bigint generated always as identity primary key,
    -- Shares the Grand Prix weekend's race row: a sprint has the same season
    -- and round as its Grand Prix.
    race_id        bigint not null references races(id) on delete cascade,
    driver_id      bigint not null references drivers(id),
    constructor_id bigint not null references constructors(id),
    position       int    not null check (position between 1 and 40),
    position_text  text,
    classification text   check (classification in ('classified','retired','disqualified','withdrawn')),
    status         text,
    points         numeric(5,2) check (points >= 0),
    grid           smallint check (grid >= 0),
    laps           smallint check (laps >= 0),
    dataset_id     bigint references datasets(id),
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now(),
    -- One classification per driver per sprint.
    unique (race_id, driver_id)
);

comment on table sprint_results is
    'Sprint races, 2021 onward. Deliberately separate from `results`: a sprint '
    'is its own event with its own grid and points scale. Merging the two '
    'would double every driver''s race count and corrupt every entry-based rate.';
comment on column sprint_results.points is
    'Sprint points only. Championship totals require results.points + this.';

create index idx_sprint_race on sprint_results(race_id);
create index idx_sprint_driver on sprint_results(driver_id);
create index idx_sprint_constructor on sprint_results(constructor_id);

alter table sprint_results enable row level security;
create policy public_read_sprint_results on sprint_results
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on sprint_results from anon, authenticated;

create trigger trg_sprint_results_updated_at before update on public.sprint_results
    for each row execute function public.set_updated_at();