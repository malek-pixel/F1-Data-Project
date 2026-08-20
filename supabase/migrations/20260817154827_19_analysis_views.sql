-- ============================================================================
-- Move the last eight endpoint definitions into the database.
--
-- These were the endpoints with no Postgres implementation, and the reason
-- given was sound: each was a metric defined only in analytics.py, so adding
-- a view would have meant defining the same number twice. The fix is not to
-- duplicate them but to MOVE them -- the definition lives here, and both
-- backends read it.
--
-- Each view below reproduces the Python exactly, including the parts that
-- look arbitrary and are not:
--
--   * The distribution percentile is nearest-rank (percentile_disc), not
--     interpolated. Positions are ordinal; an interpolated "position 7.5" is
--     not a thing that can happen.
--   * Spread is sample stddev, not population: a driver's entries are a
--     sample of possible results, not every race they could have run.
--   * Spread and IQR are NULL below 5 entries rather than computed, so a
--     two-race driver does not get a confident-looking variance.
--   * Search excludes the three withheld constructors from the browsable
--     index only. They keep their rows and every aggregate still counts them.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Search: one row per findable entity.
--
-- PostgREST cannot join across tables in a single request, which is why this
-- endpoint had no implementation. A union view gives it one table to filter,
-- and `ilike` on `label` does the matching.
-- ---------------------------------------------------------------------------
create or replace view v_search_index as
    select 'driver'::text as kind,
           d.id,
           d.slug,
           d.display_name as label,
           count(*) filter (where r."position" = 1) as wins,
           lower(d.display_name) as search_key
      from drivers d
      left join results r on r.driver_id = d.id
     group by d.id, d.slug, d.display_name
    union all
    select 'constructor',
           co.id,
           co.slug,
           co.constructor_name,
           count(*) filter (where r."position" = 1),
           lower(co.constructor_name)
      from constructors co
      left join results r on r.constructor_id = co.id
     -- Withheld from the browsable index only; their results still count
     -- everywhere else. Mirrors analytics.HIDDEN_CONSTRUCTORS.
     where co.constructor_name not in ('RB F1 Team', 'Benetton', 'BAR')
     group by co.id, co.slug, co.constructor_name
    union all
    select 'circuit',
           c.id,
           c.circuit_key,
           c.circuit_name,
           null::bigint,
           lower(c.circuit_name)
      from circuits c;

comment on view v_search_index is
    'One row per findable entity, so PostgREST can search without a join. '
    'Filter with label=ilike.*term*; rank client-side by match position then wins.';


-- ---------------------------------------------------------------------------
-- Season dominance: how concentrated a season was.
--
-- win_share and points_share are NOT on a common scale and must not be
-- compared with each other. Every scoring finisher dilutes points_share, so
-- it is bounded far below 1.0 even in a season one driver dominated -- 2023
-- is 0.86 win share against 0.24 points share, and that gap is arithmetic
-- rather than a finding. Compare each against the same measure in another
-- season.
-- ---------------------------------------------------------------------------
create or replace view v_season_dominance as
    with season_races as (
        select s.year as season, count(*) as races
          from races ra join seasons s on s.id = ra.season_id
         group by s.year
    ),
    driver_totals as (
        select s.year as season, d.id, d.slug, d.display_name as name,
               count(*) filter (where r."position" = 1) as wins,
               coalesce(sum(r.points), 0) as points
          from results r
          join races ra  on ra.id = r.race_id
          join seasons s on s.id = ra.season_id
          join drivers d on d.id = r.driver_id
         group by s.year, d.id, d.slug, d.display_name
    )
    select sr.season,
           sr.races,
           count(*) filter (where dt.wins > 0) as distinct_driver_winners,
           max(dt.wins)::numeric / nullif(sr.races, 0) as top_driver_win_share,
           -- NULL rather than 0 when a season scored nothing at all, so "no
           -- points data" stays distinguishable from "nobody scored".
           max(dt.points) / nullif(sum(dt.points), 0) as top_driver_points_share,
           sum(dt.points) as total_points
      from season_races sr
      join driver_totals dt on dt.season = sr.season
     group by sr.season, sr.races;


-- ---------------------------------------------------------------------------
-- Era summary: decade-level aggregates.
--
-- Periods, not a ranking. Regulations, calendar length, field size and
-- scoring all changed across these boundaries, so the rows describe each
-- period rather than ranking them against each other.
-- ---------------------------------------------------------------------------
create or replace view v_era_summary as
    select (s.year / 10) * 10 as decade,
           ((s.year / 10) * 10)::text || 's' as label,
           count(distinct s.year)        as seasons,
           count(distinct ra.id)         as races,
           count(distinct r.driver_id)   as drivers,
           count(distinct r.constructor_id) as constructors,
           round(avg(r."position"), 3)   as avg_field_position,
           max(r."position")             as largest_field
      from results r
      join races ra  on ra.id = r.race_id
      join seasons s on s.id = ra.season_id
     group by (s.year / 10) * 10;

create or replace view v_era_top_winners as
    select decade, slug, name, wins
      from (
        select (s.year / 10) * 10 as decade,
               d.slug, d.display_name as name,
               count(*) as wins,
               row_number() over (
                   partition by (s.year / 10) * 10
                   order by count(*) desc, d.display_name
               ) as rank
          from results r
          join races ra  on ra.id = r.race_id
          join seasons s on s.id = ra.season_id
          join drivers d on d.id = r.driver_id
         where r."position" = 1
         group by (s.year / 10) * 10, d.id, d.slug, d.display_name
      ) ranked
     where rank <= 3;


-- ---------------------------------------------------------------------------
-- Finishing distribution, per driver.
--
-- The mean hides the difference between a driver reliably 5th and one
-- alternating podiums with retirements. Median and spread separate them.
--
-- Buckets match how results are actually discussed: the podium, the
-- points-paying region, and everything behind it.
-- ---------------------------------------------------------------------------
create or replace view v_driver_position_distribution as
    select d.id as driver_id,
           d.slug as driver_slug,
           d.display_name,
           count(*) as entries,
           percentile_disc(0.5) within group (order by r."position") as median,
           -- Sample, not population; NULL below 5 entries rather than a
           -- confident-looking number from almost no data.
           case when count(*) >= 5 then round(stddev_samp(r."position"), 3) end as stdev,
           count(*) >= 5 as spread_reliable,
           case when count(*) >= 5 then
               percentile_disc(0.75) within group (order by r."position")
             - percentile_disc(0.25) within group (order by r."position")
           end as iqr,
           max(r."position") as worst,
           count(*) filter (where r."position" = 1)                    as p1,
           count(*) filter (where r."position" between 2 and 3)        as p2_p3,
           count(*) filter (where r."position" between 4 and 5)        as p4_p5,
           count(*) filter (where r."position" between 6 and 10)       as p6_p10,
           count(*) filter (where r."position" between 11 and 15)      as p11_p15,
           count(*) filter (where r."position" >= 16)                  as p16_plus
      from results r
      join drivers d on d.id = r.driver_id
     group by d.id, d.slug, d.display_name;


-- ---------------------------------------------------------------------------
-- Dataset availability, COUNTED rather than listed.
--
-- This is the whole point of the endpoint: a hand-maintained list of what is
-- missing becomes wrong the moment something is ingested, which is exactly
-- what happened to this project's absent-list more than once. Every row here
-- is a count, so it cannot claim a dataset is missing when the table has rows.
-- ---------------------------------------------------------------------------
create or replace view v_dataset_availability as
    select 'race_results'       as dataset, count(*) as rows_present from results
    union all select 'championship_points', count(*) from results where points is not null
    union all select 'finishing_status',    count(*) from results where status is not null
    union all select 'grid_positions',      count(*) from results where grid is not null
    union all select 'laps_completed',      count(*) from results where laps is not null
    union all select 'qualifying',          count(*) from qualifying_results
    union all select 'sprints',             count(*) from sprint_results
    union all select 'pit_stops',           count(*) from pit_stops
    union all select 'lap_times',           count(*) from lap_times
    union all select 'sessions',            count(*) from sessions
    union all select 'cars',                count(*) from cars;

comment on view v_dataset_availability is
    'Row counts per dataset. A dataset is absent when its count is 0 -- never '
    'because a list somewhere says so.';


-- Explicit read grants. Views inherit from their base tables, but a new view
-- should never be readable only by accident -- and these were originally run
-- outside the recorded migration, which left the file and the database's own
-- record describing different DDL. Recorded here so the two match.
grant select on v_search_index                 to anon, authenticated;
grant select on v_season_dominance             to anon, authenticated;
grant select on v_era_summary                  to anon, authenticated;
grant select on v_era_top_winners              to anon, authenticated;
grant select on v_driver_position_distribution to anon, authenticated;
grant select on v_dataset_availability         to anon, authenticated;
