-- ---------------------------------------------------------------------------
-- 22. Close the gaps the payload-parity suite was never actually testing.
--
-- WHY THIS EXISTS
-- ---------------
-- test_api_payload_parity.py built both TestClients up front, but
-- `backends.selected()` reads F1_BACKEND per REQUEST, not at import. Whichever
-- value was set last answered for both clients, so every comparison ran
-- Supabase against Supabase and passed while proving nothing. Sixteen of the
-- nineteen dispatched endpoints in fact disagreed.
--
-- Five of those disagreements were missing columns here, not bugs in Python:
--
--   1. standings carried no `entries`   -> served null where SQLite serves a
--                                          verified count. "Unavailable" shown
--                                          for data that exists.
--   2. v_constructor_season_stats had no `win_rate` or `best_classified_position`
--                                       -> same, on every constructor season.
--   3. v_season_dominance had only the driver half -> the API dropped
--                                          `constructors`, `drivers`,
--                                          `distinct_constructor_winners` and
--                                          both constructor shares entirely.
--   4. driver_constructor_history read raw `driver_constructor_seasons`
--                                       -> {constructor_id, season_id,
--                                          race_count} instead of a stat block,
--                                          leaking a raw FK into the contract.
--   5. v_search_index held no race or season rows -> "ham" returned 3 hits
--                                          against SQLite's 11.
--
-- The fix is to move the missing definitions INTO the database rather than
-- recompute them in supabase_repo.py, for the reason migration 19 gives: a
-- metric defined twice is a metric that can disagree with itself.
--
-- Every view below is `security_invoker` and granted to anon/authenticated
-- read-only, matching migrations 08 and 19. No table is written.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Championship standings gain an entry count.
--
-- `entries` counts RACE classifications only: count(position) ignores the
-- NULL-position sprint rows the UNION contributes, exactly as SQLite's
-- COUNT(scored.position) does. Sprints still contribute their points.
-- ---------------------------------------------------------------------------
create or replace view v_driver_standings
with (security_invoker = true) as
 WITH scored AS (
         SELECT s.year AS season, r.driver_id, r.points, r."position"
           FROM results r
             JOIN races ra ON ra.id = r.race_id
             JOIN seasons s ON s.id = ra.season_id
        UNION ALL
         SELECT s.year, sp.driver_id, sp.points, NULL::integer
           FROM sprint_results sp
             JOIN races ra ON ra.id = sp.race_id
             JOIN seasons s ON s.id = ra.season_id
        )
 SELECT scored.season,
    d.id AS driver_id,
    d.display_name,
    sum(scored.points) AS points,
    count(*) FILTER (WHERE scored."position" = 1) AS wins,
    count(*) FILTER (WHERE scored."position" <= 3) AS podiums,
    rank() OVER (PARTITION BY scored.season ORDER BY (sum(scored.points)) DESC,
                 (count(*) FILTER (WHERE scored."position" = 1)) DESC) AS points_rank,
    d.slug AS driver_slug,
    -- Appended, not inserted: CREATE OR REPLACE VIEW may only add columns at
    -- the end. Counting `position` ignores the NULL-position sprint rows the
    -- UNION contributes, exactly as SQLite's COUNT(scored.position) does.
    count(scored."position") AS entries
   FROM scored
     JOIN drivers d ON d.id = scored.driver_id
  GROUP BY scored.season, d.id;

create or replace view v_constructor_standings
with (security_invoker = true) as
 WITH scored AS (
         SELECT s.year AS season, r.constructor_id, r.points, r."position"
           FROM results r
             JOIN races ra ON ra.id = r.race_id
             JOIN seasons s ON s.id = ra.season_id
        UNION ALL
         SELECT s.year, sp.constructor_id, sp.points, NULL::integer
           FROM sprint_results sp
             JOIN races ra ON ra.id = sp.race_id
             JOIN seasons s ON s.id = ra.season_id
        )
 SELECT scored.season,
    co.id AS constructor_id,
    co.constructor_name,
    sum(scored.points) AS points,
    count(*) FILTER (WHERE scored."position" = 1) AS wins,
    count(*) FILTER (WHERE scored."position" <= 3) AS podiums,
    rank() OVER (PARTITION BY scored.season ORDER BY (sum(scored.points)) DESC,
                 (count(*) FILTER (WHERE scored."position" = 1)) DESC) AS points_rank,
    co.slug AS constructor_slug,
    count(scored."position") AS entries
   FROM scored
     JOIN constructors co ON co.id = scored.constructor_id
  GROUP BY scored.season, co.id;


-- ---------------------------------------------------------------------------
-- 2. Constructor season stats gain the two columns the stat block expects.
--
-- Everything else is carried forward from migration 18 unchanged; only
-- win_rate and best_classified_position are added. Column order is preserved
-- so nothing reading positionally shifts.
-- ---------------------------------------------------------------------------
create or replace view v_constructor_season_stats
with (security_invoker = true) as
 SELECT co.id AS constructor_id,
    co.constructor_name,
    s.year AS season,
    count(*) AS entries,
    count(DISTINCT r.race_id) AS races_contested,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    round(avg(r."position"), 3) AS avg_classified_position,
    co.slug AS constructor_slug,
    count(*) FILTER (WHERE r."position" <= 10) AS top10,
    count(*) FILTER (WHERE r."position" <= 5) AS top5,
    count(*) FILTER (WHERE r."position" <= 3)::numeric / NULLIF(count(*), 0)::numeric AS podium_rate,
    count(*) FILTER (WHERE r."position" <= 5)::numeric / NULLIF(count(*), 0)::numeric AS top5_rate,
    count(*) FILTER (WHERE r."position" <= 10)::numeric / NULLIF(count(*), 0)::numeric AS top10_rate,
    count(r.classification) AS enriched,
    count(*) FILTER (WHERE r.classification = 'classified') AS finishes,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified') AS dnfs,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified')::numeric
        / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    round(avg(r.grid) FILTER (WHERE r.grid > 0), 3) AS avg_grid,
    round(avg(r.grid - r."position") FILTER (WHERE r.grid > 0 AND r.classification = 'classified'), 3)
        AS avg_positions_gained,
    -- Added by migration 22.
    count(*) FILTER (WHERE r."position" = 1)::numeric / NULLIF(count(*), 0)::numeric AS win_rate,
    min(r."position") AS best_classified_position
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id, s.year;


-- ---------------------------------------------------------------------------
-- 3. A driver's constructor history, as a stat block per (season, constructor).
--
-- Replaces reading `driver_constructor_seasons` directly, which carried only
-- race_count and a raw season_id FK. A mid-season switch is two rows, never
-- merged -- same rule as analytics.driver_constructor_history.
-- ---------------------------------------------------------------------------
create or replace view v_driver_constructor_seasons
with (security_invoker = true) as
 SELECT d.id AS driver_id,
    d.slug AS driver_slug,
    s.year AS season,
    co.id AS constructor_id,
    co.slug AS constructor_slug,
    co.constructor_name,
    count(*) AS entries,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    count(*) FILTER (WHERE r."position" <= 5) AS top5,
    count(*) FILTER (WHERE r."position" <= 10) AS top10,
    count(*) FILTER (WHERE r."position" = 1)::numeric / NULLIF(count(*), 0)::numeric AS win_rate,
    count(*) FILTER (WHERE r."position" <= 3)::numeric / NULLIF(count(*), 0)::numeric AS podium_rate,
    count(*) FILTER (WHERE r."position" <= 5)::numeric / NULLIF(count(*), 0)::numeric AS top5_rate,
    count(*) FILTER (WHERE r."position" <= 10)::numeric / NULLIF(count(*), 0)::numeric AS top10_rate,
    round(avg(r."position"), 3) AS avg_classified_position,
    min(r."position") AS best_classified_position,
    count(r.classification) AS enriched,
    count(*) FILTER (WHERE r.classification = 'classified') AS finishes,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified') AS dnfs,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified')::numeric
        / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    round(avg(r.grid) FILTER (WHERE r.grid > 0), 3) AS avg_grid,
    round(avg(r.grid - r."position") FILTER (WHERE r.grid > 0 AND r.classification = 'classified'), 3)
        AS avg_positions_gained
   FROM results r
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
     JOIN drivers d ON d.id = r.driver_id
     JOIN constructors co ON co.id = r.constructor_id
  GROUP BY d.id, d.slug, s.year, co.id, co.slug, co.constructor_name;


-- ---------------------------------------------------------------------------
-- 4. Season dominance gains its constructor half.
--
-- The driver scalars are unchanged. `total_points` is kept for compatibility.
--
-- win_share and points_share are NOT comparable with each other: every scoring
-- finisher dilutes points_share, so it is bounded far below 1.0 however
-- dominant the leader was. Both are reported; neither refines the other.
-- ---------------------------------------------------------------------------
create or replace view v_season_dominance
with (security_invoker = true) as
    with season_races as (
        select s.year as season, count(*) as races
          from races ra join seasons s on s.id = ra.season_id
         group by s.year
    ),
    driver_totals as (
        select s.year as season, d.id,
               count(*) filter (where r."position" = 1) as wins,
               coalesce(sum(r.points), 0) as points
          from results r
          join races ra  on ra.id = r.race_id
          join seasons s on s.id = ra.season_id
          join drivers d on d.id = r.driver_id
         group by s.year, d.id
    ),
    constructor_totals as (
        select s.year as season, co.id,
               count(*) filter (where r."position" = 1) as wins,
               coalesce(sum(r.points), 0) as points
          from results r
          join races ra  on ra.id = r.race_id
          join seasons s on s.id = ra.season_id
          join constructors co on co.id = r.constructor_id
         group by s.year, co.id
    ),
    driver_agg as (
        select dt.season,
               count(*) filter (where dt.wins > 0) as distinct_driver_winners,
               max(dt.wins) as top_driver_wins,
               max(dt.points) as top_driver_points,
               sum(dt.points) as total_points
          from driver_totals dt group by dt.season
    ),
    constructor_agg as (
        select ct.season,
               count(*) filter (where ct.wins > 0) as distinct_constructor_winners,
               max(ct.wins) as top_constructor_wins,
               max(ct.points) as top_constructor_points,
               sum(ct.points) as total_constructor_points
          from constructor_totals ct group by ct.season
    )
    select sr.season,
           sr.races,
           da.distinct_driver_winners,
           da.top_driver_wins::numeric / nullif(sr.races, 0) as top_driver_win_share,
           -- NULL rather than 0 when a season scored nothing at all, so "no
           -- points data" stays distinguishable from "nobody scored".
           da.top_driver_points / nullif(da.total_points, 0) as top_driver_points_share,
           da.total_points,
           ca.distinct_constructor_winners,
           ca.top_constructor_wins::numeric / nullif(sr.races, 0) as top_constructor_win_share,
           ca.top_constructor_points / nullif(ca.total_constructor_points, 0)
               as top_constructor_points_share
      from season_races sr
      join driver_agg da      on da.season = sr.season
      join constructor_agg ca on ca.season = sr.season;


-- ---------------------------------------------------------------------------
-- 5. The per-entity rows dominance lists alongside those scalars.
--
-- `win_share` is this entity's wins over races HELD, so a season's shares sum
-- to 1.0 across winners and below it across all entrants.
-- ---------------------------------------------------------------------------
create or replace view v_season_dominance_drivers
with (security_invoker = true) as
    with season_races as (
        select s.year as season, count(*) as races
          from races ra join seasons s on s.id = ra.season_id
         group by s.year
    )
    select s.year as season,
           d.id, d.slug, d.display_name as name,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) as entries,
           round(avg(r."position"), 3) as avg_classified_position,
           count(*) filter (where r."position" = 1)::numeric
               / nullif(sr.races, 0) as win_share,
           sum(r.points) as points
      from results r
      join races ra  on ra.id = r.race_id
      join seasons s on s.id = ra.season_id
      join drivers d on d.id = r.driver_id
      join season_races sr on sr.season = s.year
     group by s.year, d.id, d.slug, d.display_name, sr.races;

create or replace view v_season_dominance_constructors
with (security_invoker = true) as
    with season_races as (
        select s.year as season, count(*) as races
          from races ra join seasons s on s.id = ra.season_id
         group by s.year
    )
    select s.year as season,
           co.id, co.slug, co.constructor_name as name,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) as entries,
           round(avg(r."position"), 3) as avg_classified_position,
           count(*) filter (where r."position" = 1)::numeric
               / nullif(sr.races, 0) as win_share,
           sum(r.points) as points
      from results r
      join races ra  on ra.id = r.race_id
      join seasons s on s.id = ra.season_id
      join constructors co on co.id = r.constructor_id
      join season_races sr on sr.season = s.year
     group by s.year, co.id, co.slug, co.constructor_name, sr.races;


-- ---------------------------------------------------------------------------
-- 6. The search index gains races and seasons.
--
-- Two key columns, because matching and ranking are different questions:
--   * match_key  -- what a query is tested against. A circuit matches on its
--                   country too, so "Belgium" finds Spa.
--   * search_key -- what prefix rank is measured on. Name only, so matching a
--                   country does not pull a circuit above an exact name hit.
-- `sublabel` is precomputed per kind because it differs by kind and the caller
-- would otherwise need a second query per row.
-- ---------------------------------------------------------------------------
create or replace view v_search_index
with (security_invoker = true) as
    select 'driver'::text as kind,
           d.id,
           d.slug,
           d.display_name as label,
           count(*) filter (where r."position" = 1) as wins,
           lower(d.display_name) as search_key,
           lower(d.display_name) as match_key,
           null::text as sublabel,
           null::int as season,
           null::int as round
      from drivers d
      left join results r on r.driver_id = d.id
     group by d.id, d.slug, d.display_name
    union all
    select 'constructor',
           co.id,
           co.slug,
           co.constructor_name,
           count(*) filter (where r."position" = 1),
           lower(co.constructor_name),
           lower(co.constructor_name),
           null::text,
           null::int,
           null::int
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
           lower(c.circuit_name),
           lower(c.circuit_name || ' ' || c.country),
           c.country,
           null::int,
           null::int
      from circuits c
    union all
    -- Race identity in this dataset is the Grand Prix name, but most people
    -- refer to a race by its circuit ("Monza", "Spa"), so both are matchable.
    select 'race',
           ra.id,
           null::text,
           s.year || ' ' || ra.race_name,
           null::bigint,
           lower(ra.race_name),
           lower(ra.race_name || ' ' || c.circuit_name),
           c.circuit_name || ' · round ' || ra.round || ' · ' || ra.race_date,
           s.year,
           ra.round
      from races ra
      join seasons s  on s.id = ra.season_id
      join circuits c on c.id = ra.circuit_id
    union all
    select 'season',
           s.year,
           null::text,
           s.year::text,
           null::bigint,
           s.year::text,
           s.year::text,
           count(ra.id) || ' races',
           s.year,
           null::int
      from seasons s
      join races ra on ra.season_id = s.id
     group by s.year;


-- ---------------------------------------------------------------------------
-- Grants. Read-only to both roles, matching every other analytical view.
-- ---------------------------------------------------------------------------
grant select on v_driver_standings              to anon, authenticated;
grant select on v_constructor_standings         to anon, authenticated;
grant select on v_constructor_season_stats      to anon, authenticated;
grant select on v_driver_constructor_seasons    to anon, authenticated;
grant select on v_season_dominance              to anon, authenticated;
grant select on v_season_dominance_drivers      to anon, authenticated;
grant select on v_season_dominance_constructors to anon, authenticated;
grant select on v_search_index                  to anon, authenticated;


-- ---------------------------------------------------------------------------
-- 8. Career-stats views: a collation-stable sort key, and the five columns
--    the constructor stat block was missing.
--
-- v_constructor_career_stats had no top5, top5_rate, top10_rate, avg_grid or
-- avg_positions_gained, so /api/constructors/{slug} served null for each while
-- SQLite served real numbers -- Ferrari's 601 top-five finishes read as
-- "unavailable". The driver view already carried all five.
--
-- Both views are defined once, here, so re-running this file is idempotent.
--
-- `?sort=name` ordered by `display_name`, which Postgres compares under the
-- database's locale collation and SQLite compares byte-by-byte. Accented names
-- land in different places -- so page 1 of the A-Z listing held different
-- drivers depending on which backend answered.
--
-- `collate "C"` is byte order, which is exactly what SQLite's default BINARY
-- collation does, so ordering by this column matches the other backend
-- character for character. It is a sort key, never displayed.
-- ---------------------------------------------------------------------------
create or replace view v_driver_career_stats
with (security_invoker = true) as
 SELECT d.id AS driver_id,
    d.driver_key,
    d.display_name,
    count(*) AS entries,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    count(*) FILTER (WHERE r."position" <= 5) AS top5,
    count(*) FILTER (WHERE r."position" <= 10) AS top10,
    count(*) FILTER (WHERE r."position" = 1)::numeric / NULLIF(count(*), 0)::numeric AS win_rate,
    count(*) FILTER (WHERE r."position" <= 3)::numeric / NULLIF(count(*), 0)::numeric AS podium_rate,
    count(*) FILTER (WHERE r."position" <= 5)::numeric / NULLIF(count(*), 0)::numeric AS top5_rate,
    count(*) FILTER (WHERE r."position" <= 10)::numeric / NULLIF(count(*), 0)::numeric AS top10_rate,
    round(avg(r."position"), 3) AS avg_classified_position,
    percentile_cont(0.5::double precision) WITHIN GROUP (ORDER BY (r."position"::double precision))
        AS median_classified_position,
        CASE
            WHEN count(*) >= 5 THEN round(stddev_samp(r."position"), 3)
            ELSE NULL::numeric
        END AS position_stdev,
    min(r."position") AS best_classified_position,
    min(s.year) AS first_season,
    max(s.year) AS last_season,
    count(*) >= 10 AS rates_reliable,
    count(r.classification) AS enriched,
    count(*) FILTER (WHERE r.classification = 'classified'::text) AS finishes,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text) AS dnfs,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text)::numeric
        / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    round(avg(r.grid) FILTER (WHERE r.grid > 0), 3) AS avg_grid,
    round(avg(r.grid - r."position") FILTER (WHERE r.grid > 0 AND r.classification = 'classified'::text), 3)
        AS avg_positions_gained,
    d.slug AS driver_slug,
    -- Added by migration 22.
    d.display_name collate "C" AS sort_name
   FROM drivers d
     JOIN results r ON r.driver_id = d.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY d.id;

create or replace view v_constructor_career_stats
with (security_invoker = true) as
 SELECT co.id AS constructor_id,
    co.constructor_key,
    co.constructor_name,
    count(*) AS entries,
    count(DISTINCT r.race_id) AS races_contested,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    count(*) FILTER (WHERE r."position" <= 10) AS top10,
    count(*) FILTER (WHERE r."position" = 1)::numeric / NULLIF(count(*), 0)::numeric AS win_rate,
    count(*) FILTER (WHERE r."position" <= 3)::numeric / NULLIF(count(*), 0)::numeric AS podium_rate,
    round(avg(r."position"), 3) AS avg_classified_position,
    min(r."position") AS best_classified_position,
    min(s.year) AS first_season,
    max(s.year) AS last_season,
    count(r.classification) AS enriched,
    count(*) FILTER (WHERE r.classification = 'classified'::text) AS finishes,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text) AS dnfs,
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text)::numeric
        / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    co.slug AS constructor_slug,
    count(*) FILTER (WHERE r."position" <= 5) AS top5,
    count(*) FILTER (WHERE r."position" <= 5)::numeric / NULLIF(count(*), 0)::numeric AS top5_rate,
    count(*) FILTER (WHERE r."position" <= 10)::numeric / NULLIF(count(*), 0)::numeric AS top10_rate,
    round(avg(r.grid) FILTER (WHERE r.grid > 0), 3) AS avg_grid,
    round(avg(r.grid - r."position") FILTER (WHERE r.grid > 0 AND r.classification = 'classified'), 3)
        AS avg_positions_gained,
    co.constructor_name collate "C" AS sort_name
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id;

grant select on v_driver_career_stats      to anon, authenticated;
grant select on v_constructor_career_stats to anon, authenticated;


-- ---------------------------------------------------------------------------
-- 9. Stat block for one entity over a season window.
--
-- /api/compare returns `left_shared` / `right_shared`: each side recomputed
-- over the seasons the two actually overlapped. The Supabase leg omitted both
-- keys entirely, so the Compare page's like-for-like panel -- the only part of
-- that page which controls for era -- had nothing to render.
--
-- It has to be a function rather than a view because the window is an
-- argument. Summing the per-season view instead would be wrong: avg_grid and
-- avg_positions_gained are means over results, and a mean of means is not the
-- mean unless every season has the same entry count.
--
-- STABLE + security invoker: read-only, and it sees exactly what the calling
-- role is allowed to see.
-- ---------------------------------------------------------------------------
create or replace function f_entity_window_stats(
    p_entity text,
    p_slug   text,
    p_from   int,
    p_to     int
)
returns table (
    entries                 bigint,
    wins                    bigint,
    podiums                 bigint,
    top5                    bigint,
    top10                   bigint,
    win_rate                numeric,
    podium_rate             numeric,
    top5_rate               numeric,
    top10_rate              numeric,
    avg_classified_position numeric,
    best_classified_position int,
    enriched                bigint,
    finishes                bigint,
    dnfs                    bigint,
    dnf_rate                numeric,
    points                  numeric,
    avg_grid                numeric,
    avg_positions_gained    numeric
)
language sql
stable
security invoker
as $$
    select count(*) as entries,
           count(*) filter (where r."position" = 1) as wins,
           count(*) filter (where r."position" <= 3) as podiums,
           count(*) filter (where r."position" <= 5) as top5,
           count(*) filter (where r."position" <= 10) as top10,
           count(*) filter (where r."position" = 1)::numeric / nullif(count(*), 0)::numeric,
           count(*) filter (where r."position" <= 3)::numeric / nullif(count(*), 0)::numeric,
           count(*) filter (where r."position" <= 5)::numeric / nullif(count(*), 0)::numeric,
           count(*) filter (where r."position" <= 10)::numeric / nullif(count(*), 0)::numeric,
           round(avg(r."position"), 3),
           min(r."position"),
           count(r.classification),
           count(*) filter (where r.classification = 'classified'),
           count(*) filter (where r.classification is not null and r.classification <> 'classified'),
           count(*) filter (where r.classification is not null and r.classification <> 'classified')::numeric
               / nullif(count(r.classification), 0)::numeric,
           sum(r.points),
           round(avg(r.grid) filter (where r.grid > 0), 3),
           round(avg(r.grid - r."position")
                 filter (where r.grid > 0 and r.classification = 'classified'), 3)
      from results r
      join races ra   on ra.id = r.race_id
      join seasons s  on s.id  = ra.season_id
      left join drivers d      on d.id  = r.driver_id
      left join constructors c on c.id  = r.constructor_id
     where s.year between p_from and p_to
       and ((p_entity = 'driver'      and d.slug = p_slug)
         or (p_entity = 'constructor' and c.slug = p_slug));
$$;

grant execute on function f_entity_window_stats(text, text, int, int) to anon, authenticated;
