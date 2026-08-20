-- ============================================================================
-- Complete the season stat block.
--
-- v_driver_season_stats and v_constructor_season_stats carried a subset of
-- the career views' columns: no top5, no rates beyond win_rate, and none of
-- the enrichment-derived fields. The constructor view had no top10 count at
-- all. Serving /api/drivers/{id}/seasons from Postgres therefore produced a
-- payload with nulls where SQLite had numbers, and the response model
-- rejected it -- which is how this gap was found, by the payload parity test
-- rather than by reading the two definitions side by side.
--
-- The expressions below are the ones analytics._STATS_SELECT uses, with the
-- same two rules carried over deliberately:
--
--   * dnf_rate divides by the count of rows CARRYING a status, never by all
--     entries. A partially enriched season must not report a rate over rows
--     it knows nothing about.
--
--   * avg_grid excludes grid = 0. A pit-lane start is a real value but not a
--     grid slot, so counting it as zero would drag the average toward the
--     front of the grid.
-- ============================================================================

create or replace view v_driver_season_stats as
 SELECT d.id AS driver_id,
    d.display_name,
    s.year AS season,
    count(*) AS entries,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    count(*) FILTER (WHERE r."position" <= 10) AS top10,
    count(*) FILTER (WHERE r."position" = 1)::numeric / NULLIF(count(*), 0)::numeric AS win_rate,
    round(avg(r."position"), 3) AS avg_classified_position,
    percentile_cont(0.5::double precision) WITHIN GROUP (ORDER BY (r."position"::double precision)) AS median_classified_position,
    min(r."position") AS best_classified_position,
    d.slug AS driver_slug,
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
        AS avg_positions_gained

   FROM drivers d
     JOIN results r ON r.driver_id = d.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY d.id, s.year;

create or replace view v_constructor_season_stats as
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
        AS avg_positions_gained

   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id, s.year;
