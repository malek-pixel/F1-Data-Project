-- ============================================================================
-- Finishing status, points, grid and laps.
--
-- Until now `results` carried one measured column: `position`, the final
-- classification order. That made a lap-1 retirement indistinguishable from a
-- genuine last place, which skewed every average and made "reliability" an
-- unanswerable question.
--
-- Source: Jolpica-F1, recorded as a second data_source. Joined to the existing
-- rows on (season, round, position) -- a key verified to align across all
-- 10,550 rows with zero driver or constructor mismatches BEFORE these columns
-- were added.
--
-- NULLABLE on purpose. Coverage is 100% for 2000-2025, but declaring NOT NULL
-- would forbid ingesting an older season where the source genuinely has gaps.
-- NULL keeps meaning "not known"; a coverage check asserts completeness for
-- the window actually loaded instead.
-- ============================================================================

alter table results
    -- The classification signal itself: a number, or R / W / D.
    add column position_text  text,
    -- Derived from position_text by a single documented rule. Kept as its own
    -- column so consumers never re-implement that parse.
    add column classification text
        check (classification in ('classified','retired','disqualified','withdrawn')),
    -- Raw source text, 104 distinct values ('Finished', '+1 Lap', 'Gearbox',
    -- 'Collision', ...). Deliberately NOT collapsed into a small enum: the
    -- detail is the value, and any bucketing is a judgement a consumer should
    -- make explicitly.
    add column status         text,
    add column points         numeric(6,2) check (points >= 0),
    -- 0 is a REAL value here: a pit-lane start. It is not "unknown".
    add column grid           smallint     check (grid >= 0),
    add column laps           smallint     check (laps >= 0);

comment on column results.position_text is
    'Source classification marker: a number when classified, else R (retired), '
    'W (withdrawn) or D (disqualified).';
comment on column results.classification is
    'Derived from position_text. "classified" is NOT "finished" -- a driver '
    'several laps down is classified. Whether they saw the flag is in status.';
comment on column results.status is
    'Raw source status, never collapsed into an enum. 104 distinct values.';
comment on column results.grid is
    'Starting position. 0 means a PIT LANE START -- a known value, not NULL. '
    'Never treat it as missing data.';
comment on column results.points is
    'Championship points awarded for this result under the scoring system in '
    'force that season. Half-point races carry their half values.';

-- Partial index: "did not finish" is the single most common new filter, and
-- retirements are ~20% of rows, so a partial index is much smaller than a
-- full one on classification.
create index idx_results_retired on results(classification)
    where classification <> 'classified';
create index idx_results_points on results(points) where points > 0;
create index idx_results_grid on results(grid);

-- Provenance for the new columns. Recorded as a distinct source, because it
-- is one: results.csv did not supply these values.
insert into data_sources (source_key, name, source_type, source_url, description)
values ('jolpica_f1', 'Jolpica-F1 (Ergast successor)', 'api',
        'https://api.jolpi.ca/ergast/f1',
        'Finishing status, points, grid and laps. Joined to results.csv on '
        '(season, round, position); alignment verified across all 10,550 rows.')
on conflict (source_key) do update set name = excluded.name,
    source_url = excluded.source_url, description = excluded.description;