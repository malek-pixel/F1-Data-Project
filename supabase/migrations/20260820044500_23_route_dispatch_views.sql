-- ---------------------------------------------------------------------------
-- 23. The primitives the remaining routes need to reach Supabase at all.
--
-- WHY THIS EXISTS
-- ---------------
-- Migration 22 fixed the endpoints that dispatched through `backends.serve`
-- and disagreed. This one addresses the larger problem sitting behind that:
-- roughly two thirds of the routes never called `serve()` in the first place.
-- They read SQLite whatever F1_BACKEND said, which is the silent fallback
-- backends.py exists to forbid -- and it also meant the payload-parity suite
-- passed on them by comparing SQLite against itself, the same vacuity as the
-- fixture bug, one layer up.
--
-- `SUPABASE_CAPABILITIES` already named several of these as supported. It was
-- measuring what supabase_repo COULD do, not what any route actually called,
-- and `test_capability_set_is_not_aspirational` only checked that a function
-- of that name existed.
--
-- Everything below is a read-only view, `security_invoker`, granted to
-- anon/authenticated, matching migrations 08, 19 and 22. No table is written.
-- Views that already existed are redefined in full with new columns APPENDED,
-- because CREATE OR REPLACE VIEW may only add columns at the end.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Race summary: one row per race with its winner.
--
-- Mirrors calendar.RACE_SELECT column for column. Serves /api/races, the
-- races_list on /api/seasons/{season}, and /api/seasons/{season}/rounds --
-- three routes that were each running the same LEFT JOIN in SQLite.
--
-- LEFT JOIN on the winner, not INNER: a race with no position-1 row in the
-- source must still appear, or the calendar silently looks shorter than the
-- season was.
--
-- `qualifying_first` is deliberately not called "pole": qualifying P1 and the
-- pole position diverge in the sprint era.
-- ---------------------------------------------------------------------------
create or replace view v_race_summary
with (security_invoker = true) as
    select ra.id,
           s.year as season,
           ra.round,
           ra.race_name as name,
           ra.race_date as date,
           ra.circuit_id,
           ci.circuit_name,
           ci.circuit_key as circuit_slug,
           d.id   as winner_driver_id,
           d.slug as winner_driver_slug,
           d.display_name as winner_driver,
           co.id   as winner_constructor_id,
           co.slug as winner_constructor_slug,
           co.constructor_name as winner_constructor,
           r.grid   as winner_grid,
           r.status as winner_status,
           pole.display_name as qualifying_first,
           pole.slug         as qualifying_first_slug
      from races ra
      join seasons s   on s.id = ra.season_id
      join circuits ci on ci.id = ra.circuit_id
      left join results r on r.race_id = ra.id and r."position" = 1
      left join drivers d on d.id = r.driver_id
      left join constructors co on co.id = r.constructor_id
      left join (
          select q.race_id, dq.display_name, dq.slug
            from qualifying_results q
            join drivers dq on dq.id = q.driver_id
           where q."position" = 1
      ) pole on pole.race_id = ra.id;


-- ---------------------------------------------------------------------------
-- 2. Circuit stats gain the full stat block and the leading winner.
--
-- /api/circuits/{id} returns the canonical stat block for a circuit, and the
-- listing carries the top winner so the circuit table renders from one
-- request rather than one request per row. Neither was expressible against
-- the old view.
--
-- The winner sub-selects are correlated but run over 39 circuits, which is
-- the same trade the SQLite listing already makes.
-- ---------------------------------------------------------------------------
create or replace view v_circuit_stats
with (security_invoker = true) as
    select ci.id as circuit_id,
           ci.circuit_key,
           ci.circuit_name,
           ci.country,
           count(distinct ra.id) as races,
           count(r.id) as entries,
           count(distinct r.driver_id) filter (where r."position" = 1) as distinct_winners,
           round(avg(r."position"), 3) as avg_classified_position,
           min(s.year) as first_season,
           max(s.year) as last_season,
           ci.svg_asset is not null as has_map,
           -- Appended by migration 23.
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) filter (where r."position" <= 5) as top5,
           count(*) filter (where r."position" <= 10) as top10,
           count(*) filter (where r."position" = 1)::numeric
               / nullif(count(r.id), 0)::numeric as win_rate,
           count(*) filter (where r."position" <= 3)::numeric
               / nullif(count(r.id), 0)::numeric as podium_rate,
           count(*) filter (where r."position" <= 5)::numeric
               / nullif(count(r.id), 0)::numeric as top5_rate,
           count(*) filter (where r."position" <= 10)::numeric
               / nullif(count(r.id), 0)::numeric as top10_rate,
           min(r."position") as best_classified_position,
           count(r.classification) as enriched,
           count(*) filter (where r.classification = 'classified') as finishes,
           count(*) filter (where r.classification is not null
                              and r.classification <> 'classified') as dnfs,
           count(*) filter (where r.classification is not null
                              and r.classification <> 'classified')::numeric
               / nullif(count(r.classification), 0)::numeric as dnf_rate,
           sum(r.points) as points,
           round(avg(r.grid) filter (where r.grid > 0), 3) as avg_grid,
           round(avg(r.grid - r."position")
                 filter (where r.grid > 0 and r.classification = 'classified'), 3)
               as avg_positions_gained,
           (select d.display_name
              from results rw
              join races raw on raw.id = rw.race_id
              join drivers d on d.id = rw.driver_id
             where raw.circuit_id = ci.id and rw."position" = 1
             group by d.id, d.display_name
             order by count(*) desc, d.display_name
             limit 1) as top_winner,
           (select count(*)
              from results rw
              join races raw on raw.id = rw.race_id
             where raw.circuit_id = ci.id and rw."position" = 1
             group by rw.driver_id
             order by count(*) desc
             limit 1) as top_winner_wins,
           ci.circuit_key as circuit_slug,
           -- Byte order, matching SQLite's default collation. Ordering by
           -- circuit_name under the database's locale collation put
           -- "Circuit de Barcelona-Catalunya" and "Circuit Gilles
           -- Villeneuve" the other way round, so the two backends returned
           -- the circuit index in different orders.
           ci.circuit_name collate "C" as sort_name
      from circuits ci
      join races ra    on ra.circuit_id = ci.id
      join seasons s   on s.id = ra.season_id
      left join results r on r.race_id = ra.id
     group by ci.id;


-- ---------------------------------------------------------------------------
-- 3. Race-by-race winners at a circuit, for the circuit page's history strip.
-- ---------------------------------------------------------------------------
create or replace view v_circuit_winners
with (security_invoker = true) as
    select ra.circuit_id,
           ra.id as race_id,
           s.year as season,
           ra.race_name,
           ra.race_date,
           d.id   as driver_id,
           d.slug as driver_slug,
           d.display_name as driver_name,
           co.id   as constructor_id,
           co.slug as constructor_slug,
           co.constructor_name as constructor_name
      from races ra
      join seasons s on s.id = ra.season_id
      left join results r on r.race_id = ra.id and r."position" = 1
      left join drivers d on d.id = r.driver_id
      left join constructors co on co.id = r.constructor_id;


-- ---------------------------------------------------------------------------
-- 4. Per-circuit leaderboards: the stat block for one entity at one circuit.
--
-- The circuit page ranks drivers and constructors by their record HERE, which
-- is a different aggregate from the career block and cannot be filtered out
-- of it.
-- ---------------------------------------------------------------------------
create or replace view v_circuit_driver_leaderboard
with (security_invoker = true) as
    select ra.circuit_id,
           d.id, d.slug, d.display_name as name,
           count(*) as entries,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) filter (where r."position" <= 5) as top5,
           count(*) filter (where r."position" <= 10) as top10,
           count(*) filter (where r."position" = 1)::numeric / nullif(count(*), 0)::numeric as win_rate,
           count(*) filter (where r."position" <= 3)::numeric / nullif(count(*), 0)::numeric as podium_rate,
           count(*) filter (where r."position" <= 5)::numeric / nullif(count(*), 0)::numeric as top5_rate,
           count(*) filter (where r."position" <= 10)::numeric / nullif(count(*), 0)::numeric as top10_rate,
           round(avg(r."position"), 3) as avg_classified_position,
           min(r."position") as best_classified_position,
           count(r.classification) as enriched,
           count(*) filter (where r.classification = 'classified') as finishes,
           count(*) filter (where r.classification is not null and r.classification <> 'classified') as dnfs,
           count(*) filter (where r.classification is not null and r.classification <> 'classified')::numeric
               / nullif(count(r.classification), 0)::numeric as dnf_rate,
           sum(r.points) as points,
           round(avg(r.grid) filter (where r.grid > 0), 3) as avg_grid,
           round(avg(r.grid - r."position") filter (where r.grid > 0 and r.classification = 'classified'), 3)
               as avg_positions_gained
      from results r
      join races ra on ra.id = r.race_id
      join drivers d on d.id = r.driver_id
     group by ra.circuit_id, d.id;

create or replace view v_circuit_constructor_leaderboard
with (security_invoker = true) as
    select ra.circuit_id,
           co.id, co.slug, co.constructor_name as name,
           count(*) as entries,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) filter (where r."position" <= 5) as top5,
           count(*) filter (where r."position" <= 10) as top10,
           count(*) filter (where r."position" = 1)::numeric / nullif(count(*), 0)::numeric as win_rate,
           count(*) filter (where r."position" <= 3)::numeric / nullif(count(*), 0)::numeric as podium_rate,
           count(*) filter (where r."position" <= 5)::numeric / nullif(count(*), 0)::numeric as top5_rate,
           count(*) filter (where r."position" <= 10)::numeric / nullif(count(*), 0)::numeric as top10_rate,
           round(avg(r."position"), 3) as avg_classified_position,
           min(r."position") as best_classified_position,
           count(r.classification) as enriched,
           count(*) filter (where r.classification = 'classified') as finishes,
           count(*) filter (where r.classification is not null and r.classification <> 'classified') as dnfs,
           count(*) filter (where r.classification is not null and r.classification <> 'classified')::numeric
               / nullif(count(r.classification), 0)::numeric as dnf_rate,
           sum(r.points) as points,
           round(avg(r.grid) filter (where r.grid > 0), 3) as avg_grid,
           round(avg(r.grid - r."position") filter (where r.grid > 0 and r.classification = 'classified'), 3)
               as avg_positions_gained
      from results r
      join races ra on ra.id = r.race_id
      join constructors co on co.id = r.constructor_id
     group by ra.circuit_id, co.id;


-- ---------------------------------------------------------------------------
-- 5. Teammate comparisons gain the constructor slug and the seasons array.
--
-- The API groups a head-to-head by constructor SPELL and lists the seasons it
-- covered. The view carried first_season/last_season only, which cannot
-- express a spell with a gap in it.
-- ---------------------------------------------------------------------------
create or replace view v_teammate_comparisons
with (security_invoker = true) as
    select me.driver_id,
        d1.display_name as driver_name,
        mate.driver_id as teammate_id,
        d2.display_name as teammate_name,
        me.constructor_id,
        co.constructor_name,
        count(*) as shared_races,
        count(*) filter (where me."position" < mate."position") as ahead,
        count(*) filter (where me."position" > mate."position") as behind,
        count(*) filter (where me."position" < mate."position")::numeric / count(*)::numeric as h2h_rate,
        round(avg(mate."position" - me."position"), 3) as avg_position_delta,
        round(avg(me."position"), 3) as my_avg_position,
        round(avg(mate."position"), 3) as teammate_avg_position,
        min(s.year) as first_season,
        max(s.year) as last_season,
        count(*) >= 5 as comparable,
        min(d1.slug) as driver_slug,
        min(d2.slug) as teammate_slug,
        -- Appended by migration 23.
        min(co.slug) as constructor_slug,
        array_agg(distinct s.year order by s.year) as seasons
       from results me
         join results mate on mate.race_id = me.race_id
                          and mate.constructor_id = me.constructor_id
                          and mate.driver_id <> me.driver_id
         join races ra on ra.id = me.race_id
         join seasons s on s.id = ra.season_id
         join drivers d1 on d1.id = me.driver_id
         join drivers d2 on d2.id = mate.driver_id
         join constructors co on co.id = me.constructor_id
      group by me.driver_id, d1.display_name, mate.driver_id, d2.display_name,
               me.constructor_id, co.constructor_name;


-- ---------------------------------------------------------------------------
-- 6. Driver-circuit stats gain the circuit slug, so the circuit column can be
--    linked without a second lookup.
-- ---------------------------------------------------------------------------
create or replace view v_driver_circuit_stats
with (security_invoker = true) as
    select d.id as driver_id,
        d.display_name,
        ci.id as circuit_id,
        ci.circuit_name,
        count(*) as appearances,
        count(*) filter (where r."position" = 1) as wins,
        count(*) filter (where r."position" <= 3) as podiums,
        round(avg(r."position"), 3) as avg_classified_position,
        min(r."position") as best_classified_position,
        round((select avg(r2."position") from results r2 where r2.driver_id = d.id)
              - avg(r."position"), 3) as delta_vs_career,
        count(*) >= 5 as meets_specialism_threshold,
        d.slug as driver_slug,
        -- Appended by migration 23.
        ci.circuit_key as circuit_slug,
        -- The driver's own career average, carried rather than left to be
        -- reconstructed as (avg_here + delta): both are rounded to 3dp, so
        -- adding them back together lands a thousandth out on some rows.
        round((select avg(r2."position") from results r2 where r2.driver_id = d.id), 3)
            as career_avg_classified_position
       from drivers d
         join results r on r.driver_id = d.id
         join races ra on ra.id = r.race_id
         join circuits ci on ci.id = ra.circuit_id
      group by d.id, ci.id;


-- ---------------------------------------------------------------------------
-- 7. Constructor finishing distribution, mirroring the driver one.
-- ---------------------------------------------------------------------------
create or replace view v_constructor_position_distribution
with (security_invoker = true) as
    select co.id as constructor_id,
        co.slug as constructor_slug,
        co.constructor_name,
        count(*) as entries,
        percentile_disc(0.5) within group (order by r."position") as median,
        case when count(*) >= 5 then round(stddev_samp(r."position"), 3) end as stdev,
        count(*) >= 5 as spread_reliable,
        case when count(*) >= 5
             then percentile_disc(0.75) within group (order by r."position")
                - percentile_disc(0.25) within group (order by r."position")
        end as iqr,
        max(r."position") as worst,
        count(*) filter (where r."position" = 1) as p1,
        count(*) filter (where r."position" between 2 and 3) as p2_p3,
        count(*) filter (where r."position" between 4 and 5) as p4_p5,
        count(*) filter (where r."position" between 6 and 10) as p6_p10,
        count(*) filter (where r."position" between 11 and 15) as p11_p15,
        count(*) filter (where r."position" >= 16) as p16_plus
       from results r
       join constructors co on co.id = r.constructor_id
      group by co.id, co.slug, co.constructor_name;


-- ---------------------------------------------------------------------------
-- 8. Season index: one row per season, matching /api/seasons.
-- ---------------------------------------------------------------------------
create or replace view v_season_index
with (security_invoker = true) as
    select s.year as season,
           count(distinct ra.id) as races,
           count(r.id) as entries,
           count(distinct r.driver_id) as drivers,
           count(distinct r.constructor_id) as constructors
      from races ra
      join seasons s on s.id = ra.season_id
      left join results r on r.race_id = ra.id
     group by s.year;


-- ---------------------------------------------------------------------------
-- Grants. Read-only to both roles, matching every other analytical view.
-- ---------------------------------------------------------------------------
grant select on v_race_summary                      to anon, authenticated;
grant select on v_circuit_stats                     to anon, authenticated;
grant select on v_circuit_winners                   to anon, authenticated;
grant select on v_circuit_driver_leaderboard        to anon, authenticated;
grant select on v_circuit_constructor_leaderboard   to anon, authenticated;
grant select on v_teammate_comparisons              to anon, authenticated;
grant select on v_driver_circuit_stats              to anon, authenticated;
grant select on v_constructor_position_distribution to anon, authenticated;
grant select on v_season_index                      to anon, authenticated;


-- ---------------------------------------------------------------------------
-- 9. Qualifying coverage boundary: the first season where qualifying is
--    essentially complete.
--
-- Measured, never a literal year. The source's early coverage is thin, and a
-- hardcoded 2003 here would be a claim nothing re-checks -- the same reason
-- coverage_span exists. "Essentially complete" is >= 95% of that season's
-- result rows having a qualifying row, matching
-- analytics.qualifying_coverage_from exactly.
-- ---------------------------------------------------------------------------
create or replace view v_qualifying_coverage
with (security_invoker = true) as
    select min(per_season.season) as coverage_from
      from (
          select s.year as season,
                 count(distinct q.id)::numeric
                   / nullif(count(distinct r.id), 0)::numeric as ratio
            from races ra
            join seasons s on s.id = ra.season_id
            left join results r on r.race_id = ra.id
            left join qualifying_results q on q.race_id = ra.id
           group by s.year
      ) per_season
     where per_season.ratio >= 0.95;

grant select on v_qualifying_coverage to anon, authenticated;


-- ---------------------------------------------------------------------------
-- 10. Driver contribution to a constructor, as a full stat block plus shares.
--
-- v_constructor_driver_contribution carried entries, wins, podiums and two
-- shares. The endpoint's contract is the canonical stat block PLUS three
-- shares, so the old view could not answer it.
--
-- Shares are of THIS constructor's own totals, so entry_share sums to 1.0
-- across its drivers, and win/podium share sum to 1.0 only when the team has
-- any. Share of points is deliberately not offered.
-- ---------------------------------------------------------------------------
create or replace view v_constructor_driver_stats
with (security_invoker = true) as
    select r.constructor_id,
           co.slug as constructor_slug,
           co.constructor_name,
           d.id as driver_id,
           d.slug as driver_slug,
           d.display_name as driver_name,
           count(*) as entries,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) filter (where r."position" <= 5) as top5,
           count(*) filter (where r."position" <= 10) as top10,
           count(*) filter (where r."position" = 1)::numeric / nullif(count(*), 0)::numeric as win_rate,
           count(*) filter (where r."position" <= 3)::numeric / nullif(count(*), 0)::numeric as podium_rate,
           count(*) filter (where r."position" <= 5)::numeric / nullif(count(*), 0)::numeric as top5_rate,
           count(*) filter (where r."position" <= 10)::numeric / nullif(count(*), 0)::numeric as top10_rate,
           round(avg(r."position"), 3) as avg_classified_position,
           min(r."position") as best_classified_position,
           count(r.classification) as enriched,
           count(*) filter (where r.classification = 'classified') as finishes,
           count(*) filter (where r.classification is not null and r.classification <> 'classified') as dnfs,
           count(*) filter (where r.classification is not null and r.classification <> 'classified')::numeric
               / nullif(count(r.classification), 0)::numeric as dnf_rate,
           sum(r.points) as points,
           round(avg(r.grid) filter (where r.grid > 0), 3) as avg_grid,
           round(avg(r.grid - r."position") filter (where r.grid > 0 and r.classification = 'classified'), 3)
               as avg_positions_gained,
           count(*)::numeric / nullif(sum(count(*)) over (partition by r.constructor_id), 0)::numeric
               as entry_share,
           count(*) filter (where r."position" = 1)::numeric
               / nullif(sum(count(*) filter (where r."position" = 1))
                        over (partition by r.constructor_id), 0)::numeric as win_share,
           count(*) filter (where r."position" <= 3)::numeric
               / nullif(sum(count(*) filter (where r."position" <= 3))
                        over (partition by r.constructor_id), 0)::numeric as podium_share
      from results r
      join drivers d on d.id = r.driver_id
      join constructors co on co.id = r.constructor_id
     group by r.constructor_id, co.slug, co.constructor_name, d.id;

grant select on v_constructor_driver_stats to anon, authenticated;
