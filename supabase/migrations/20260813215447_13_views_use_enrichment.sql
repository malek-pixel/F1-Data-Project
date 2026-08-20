-- ============================================================================
-- Bring the analytical views up to the enriched schema.
--
-- Migration 06 defined these views when `position` was the only measured
-- column. Migrations 10-12 added finishing status, points, grid, laps,
-- sprints and qualifying, and `backend/app/analytics.py` was updated to use
-- them -- but these views were not. The two implementations had drifted, which
-- breaks this project's rule that a metric has exactly one definition.
--
-- Columns are APPENDED, never reordered: CREATE OR REPLACE VIEW requires the
-- existing prefix to match, and any consumer selecting by position keeps
-- working.
--
-- Denominators are deliberate:
--   * rates over entries      -- every row has a position
--   * dnf_rate over enriched  -- COUNT(classification) ignores NULLs, so a
--                                partially enriched build reports a rate only
--                                over rows it actually knows about.
-- ============================================================================

create or replace view v_driver_career_stats as
select d.id as driver_id, d.driver_key, d.display_name,
       count(*)                                                    as entries,
       count(*) filter (where r.position = 1)                      as wins,
       count(*) filter (where r.position <= 3)                     as podiums,
       count(*) filter (where r.position <= 5)                     as top5,
       count(*) filter (where r.position <= 10)                    as top10,
       (count(*) filter (where r.position = 1))::numeric  / nullif(count(*),0) as win_rate,
       (count(*) filter (where r.position <= 3))::numeric / nullif(count(*),0) as podium_rate,
       (count(*) filter (where r.position <= 5))::numeric / nullif(count(*),0) as top5_rate,
       (count(*) filter (where r.position <= 10))::numeric/ nullif(count(*),0) as top10_rate,
       round(avg(r.position)::numeric, 3)                          as avg_classified_position,
       percentile_cont(0.5) within group (order by r.position)     as median_classified_position,
       case when count(*) >= 5 then round(stddev_samp(r.position)::numeric, 3) end as position_stdev,
       min(r.position)                                             as best_classified_position,
       min(s.year)                                                 as first_season,
       max(s.year)                                                 as last_season,
       count(*) >= 10                                              as rates_reliable,
       -- appended by migration 13
       count(r.classification)                                     as enriched,
       count(*) filter (where r.classification = 'classified')     as finishes,
       count(*) filter (where r.classification is not null
                          and r.classification <> 'classified')    as dnfs,
       (count(*) filter (where r.classification is not null
                           and r.classification <> 'classified'))::numeric
         / nullif(count(r.classification), 0)                      as dnf_rate,
       sum(r.points)                                               as points,
       -- grid 0 is a pit-lane start: a real value, but not a grid slot, so it
       -- is excluded from the average rather than dragging it toward zero.
       round(avg(r.grid) filter (where r.grid > 0)::numeric, 3)    as avg_grid,
       -- Classified finishes only: a retirement has no meaningful finishing
       -- position to subtract from.
       round(avg(r.grid - r.position) filter
             (where r.grid > 0 and r.classification = 'classified')::numeric, 3)
                                                                   as avg_positions_gained
from drivers d
join results r on r.driver_id = d.id
join races ra  on ra.id = r.race_id
join seasons s on s.id = ra.season_id
group by d.id;

create or replace view v_constructor_career_stats as
select co.id as constructor_id, co.constructor_key, co.constructor_name,
       count(*)                                                     as entries,
       count(distinct r.race_id)                                    as races_contested,
       count(*) filter (where r.position = 1)                       as wins,
       count(*) filter (where r.position <= 3)                      as podiums,
       count(*) filter (where r.position <= 10)                     as top10,
       (count(*) filter (where r.position = 1))::numeric  / nullif(count(*),0) as win_rate,
       (count(*) filter (where r.position <= 3))::numeric / nullif(count(*),0) as podium_rate,
       round(avg(r.position)::numeric, 3)                           as avg_classified_position,
       min(r.position)                                              as best_classified_position,
       min(s.year) as first_season, max(s.year) as last_season,
       -- appended by migration 13
       count(r.classification)                                      as enriched,
       count(*) filter (where r.classification = 'classified')      as finishes,
       count(*) filter (where r.classification is not null
                          and r.classification <> 'classified')     as dnfs,
       (count(*) filter (where r.classification is not null
                           and r.classification <> 'classified'))::numeric
         / nullif(count(r.classification), 0)                       as dnf_rate,
       sum(r.points)                                                as points
from constructors co
join results r on r.constructor_id = co.id
join races ra  on ra.id = r.race_id
join seasons s on s.id = ra.season_id
group by co.id;

-- ---------------------------------------------------------------- standings
-- CALCULATED, never stored. A stored standings table can silently disagree
-- with the rows it came from; this cannot.
--
-- Sprint points are part of the championship from 2021. Summing race points
-- alone was short by exactly 7/21/45/38/29 in 2021-2025, which is how the
-- missing sprint dataset was found in the first place.
--
-- Position is a plain points ranking. It is NOT the official classification:
-- countback tie-breaks (most wins, then most seconds, ...) are not applied, so
-- two drivers level on points are ordered by wins here as an approximation and
-- the column is named accordingly.
create or replace view v_driver_standings as
with scored as (
    select s.year as season, r.driver_id, r.points, r.position
      from results r
      join races ra on ra.id = r.race_id
      join seasons s on s.id = ra.season_id
    union all
    select s.year, sp.driver_id, sp.points, null::int
      from sprint_results sp
      join races ra on ra.id = sp.race_id
      join seasons s on s.id = ra.season_id
)
select season,
       d.id as driver_id, d.display_name,
       sum(points)                                   as points,
       count(*) filter (where position = 1)          as wins,
       count(*) filter (where position <= 3)         as podiums,
       rank() over (partition by season
                    order by sum(points) desc,
                             count(*) filter (where position = 1) desc)
                                                     as points_rank
from scored
join drivers d on d.id = scored.driver_id
group by season, d.id;

comment on view v_driver_standings is
    'Championship points by season, race + sprint. points_rank is a points '
    'ranking, NOT the official classification: countback tie-breaks are not '
    'applied. Verified to reproduce the official champion and exact points '
    'total for all 26 seasons.';

create or replace view v_constructor_standings as
with scored as (
    select s.year as season, r.constructor_id, r.points, r.position
      from results r
      join races ra on ra.id = r.race_id
      join seasons s on s.id = ra.season_id
    union all
    select s.year, sp.constructor_id, sp.points, null::int
      from sprint_results sp
      join races ra on ra.id = sp.race_id
      join seasons s on s.id = ra.season_id
)
select season,
       co.id as constructor_id, co.constructor_name,
       sum(points)                                   as points,
       count(*) filter (where position = 1)          as wins,
       count(*) filter (where position <= 3)         as podiums,
       rank() over (partition by season
                    order by sum(points) desc,
                             count(*) filter (where position = 1) desc)
                                                     as points_rank
from scored
join constructors co on co.id = scored.constructor_id
group by season, co.id;

-- ---------------------------------------------------------------- qualifying
-- Named "qualifying_p1", NOT "poles". Counting qualifying P1 gives Hamilton
-- 107 against an official 104: two are sprint weekends where 2021 awarded pole
-- to the sprint winner, and one is still unexplained. Until that is resolved
-- this must not be published as a pole count.
create or replace view v_driver_qualifying_stats as
select d.id as driver_id, d.display_name,
       count(*)                                      as qualifying_entries,
       count(*) filter (where q.position = 1)        as qualifying_p1,
       round(avg(q.position)::numeric, 3)            as avg_qualifying_position,
       min(q.position)                               as best_qualifying_position,
       min(s.year) as first_season, max(s.year) as last_season
from drivers d
join qualifying_results q on q.driver_id = d.id
join races ra  on ra.id = q.race_id
join seasons s on s.id = ra.season_id
group by d.id;

comment on view v_driver_qualifying_stats is
    'qualifying_p1 is the count of fastest-qualifier classifications. It is '
    'deliberately NOT called "poles": the two differ in the sprint era and a '
    'residual discrepancy is unresolved.';

-- Views default to SECURITY DEFINER; re-assert invoker rights so none of these
-- can become a way around RLS on their base tables.
alter view v_driver_career_stats        set (security_invoker = true);
alter view v_constructor_career_stats   set (security_invoker = true);
alter view v_driver_standings           set (security_invoker = true);
alter view v_constructor_standings      set (security_invoker = true);
alter view v_driver_qualifying_stats    set (security_invoker = true);

grant select on v_driver_standings, v_constructor_standings,
                v_driver_qualifying_stats to anon, authenticated;