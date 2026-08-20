-- ============================================================================
-- Expose the portable identity through the analytical views.
--
-- Migration 15 added `slug` to drivers and constructors -- the upstream
-- source's own id, and the only identifier that addresses the same entity in
-- both this store and the SQLite build. The views still projected only
-- `driver_key` / `display_name`, so anything reading through PostgREST could
-- not obtain the portable key without a second query, and a payload served
-- from Postgres could not be compared field-for-field with the SQLite one.
--
-- Each view below is its own current definition with the slug column appended.
-- The bodies were taken from pg_get_viewdef rather than retyped, so this
-- migration cannot silently alter an aggregate while adding a column. Columns
-- are appended, never reordered, which is what CREATE OR REPLACE VIEW permits
-- and what keeps existing consumers working.
--
-- v_teammate_comparisons aggregates its slugs: it groups on the comparison
-- keys rather than on a driver primary key, so a bare column reference is not
-- valid there. min() is deterministic -- a driver has exactly one slug.
-- ============================================================================

create or replace view v_driver_career_stats as
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
    percentile_cont(0.5::double precision) WITHIN GROUP (ORDER BY (r."position"::double precision)) AS median_classified_position,
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
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text)::numeric / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    round(avg(r.grid) FILTER (WHERE r.grid > 0), 3) AS avg_grid,
    round(avg(r.grid - r."position") FILTER (WHERE r.grid > 0 AND r.classification = 'classified'::text), 3) AS avg_positions_gained,
    d.slug AS driver_slug
   FROM drivers d
     JOIN results r ON r.driver_id = d.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY d.id;

create or replace view v_constructor_career_stats as
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
    count(*) FILTER (WHERE r.classification IS NOT NULL AND r.classification <> 'classified'::text)::numeric / NULLIF(count(r.classification), 0)::numeric AS dnf_rate,
    sum(r.points) AS points,
    co.slug AS constructor_slug
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id;

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
    d.slug AS driver_slug
   FROM drivers d
     JOIN results r ON r.driver_id = d.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY d.id, s.year;

create or replace view v_driver_standings as
 WITH scored AS (
         SELECT s.year AS season,
            r.driver_id,
            r.points,
            r."position"
           FROM results r
             JOIN races ra ON ra.id = r.race_id
             JOIN seasons s ON s.id = ra.season_id
        UNION ALL
         SELECT s.year,
            sp.driver_id,
            sp.points,
            NULL::integer AS int4
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
    rank() OVER (PARTITION BY scored.season ORDER BY (sum(scored.points)) DESC, (count(*) FILTER (WHERE scored."position" = 1)) DESC) AS points_rank,
    d.slug AS driver_slug
   FROM scored
     JOIN drivers d ON d.id = scored.driver_id
  GROUP BY scored.season, d.id;

create or replace view v_constructor_standings as
 WITH scored AS (
         SELECT s.year AS season,
            r.constructor_id,
            r.points,
            r."position"
           FROM results r
             JOIN races ra ON ra.id = r.race_id
             JOIN seasons s ON s.id = ra.season_id
        UNION ALL
         SELECT s.year,
            sp.constructor_id,
            sp.points,
            NULL::integer AS int4
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
    rank() OVER (PARTITION BY scored.season ORDER BY (sum(scored.points)) DESC, (count(*) FILTER (WHERE scored."position" = 1)) DESC) AS points_rank,
    co.slug AS constructor_slug
   FROM scored
     JOIN constructors co ON co.id = scored.constructor_id
  GROUP BY scored.season, co.id;

create or replace view v_constructor_season_stats as
 SELECT co.id AS constructor_id,
    co.constructor_name,
    s.year AS season,
    count(*) AS entries,
    count(DISTINCT r.race_id) AS races_contested,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    round(avg(r."position"), 3) AS avg_classified_position,
    co.slug AS constructor_slug
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id, s.year;

create or replace view v_driver_qualifying_stats as
 SELECT d.id AS driver_id,
    d.display_name,
    count(*) AS qualifying_entries,
    count(*) FILTER (WHERE q."position" = 1) AS qualifying_p1,
    round(avg(q."position"), 3) AS avg_qualifying_position,
    min(q."position") AS best_qualifying_position,
    min(s.year) AS first_season,
    max(s.year) AS last_season,
    d.slug AS driver_slug
   FROM drivers d
     JOIN qualifying_results q ON q.driver_id = d.id
     JOIN races ra ON ra.id = q.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY d.id;

create or replace view v_driver_circuit_stats as
 SELECT d.id AS driver_id,
    d.display_name,
    ci.id AS circuit_id,
    ci.circuit_name,
    count(*) AS appearances,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    round(avg(r."position"), 3) AS avg_classified_position,
    min(r."position") AS best_classified_position,
    round((( SELECT avg(r2."position") AS avg
           FROM results r2
          WHERE r2.driver_id = d.id)) - avg(r."position"), 3) AS delta_vs_career,
    count(*) >= 5 AS meets_specialism_threshold,
    d.slug AS driver_slug
   FROM drivers d
     JOIN results r ON r.driver_id = d.id
     JOIN races ra ON ra.id = r.race_id
     JOIN circuits ci ON ci.id = ra.circuit_id
  GROUP BY d.id, ci.id;

create or replace view v_constructor_driver_contribution as
 SELECT co.id AS constructor_id,
    co.constructor_name,
    d.id AS driver_id,
    d.display_name AS driver_name,
    count(*) AS entries,
    count(*) FILTER (WHERE r."position" = 1) AS wins,
    count(*) FILTER (WHERE r."position" <= 3) AS podiums,
    count(*)::numeric / sum(count(*)) OVER (PARTITION BY co.id) AS entry_share,
    NULLIF(count(*) FILTER (WHERE r."position" = 1), 0)::numeric / NULLIF(sum(count(*) FILTER (WHERE r."position" = 1)) OVER (PARTITION BY co.id), 0::numeric) AS win_share,
    d.slug AS driver_slug,
    co.slug AS constructor_slug
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN drivers d ON d.id = r.driver_id
  GROUP BY co.id, d.id;

create or replace view v_race_results as
 SELECT r.id AS result_id,
    ra.id AS race_id,
    s.year AS season,
    ra.round,
    ra.race_name,
    ra.race_date,
    ci.id AS circuit_id,
    ci.circuit_name,
    ci.circuit_key,
    d.id AS driver_id,
    d.display_name AS driver_name,
    d.driver_key,
    co.id AS constructor_id,
    co.constructor_name,
    co.constructor_key,
    r."position",
    d.slug AS driver_slug,
    co.slug AS constructor_slug
   FROM results r
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
     JOIN circuits ci ON ci.id = ra.circuit_id
     JOIN drivers d ON d.id = r.driver_id
     JOIN constructors co ON co.id = r.constructor_id;

create or replace view v_teammate_comparisons as
 SELECT me.driver_id,
    d1.display_name AS driver_name,
    mate.driver_id AS teammate_id,
    d2.display_name AS teammate_name,
    me.constructor_id,
    co.constructor_name,
    count(*) AS shared_races,
    count(*) FILTER (WHERE me."position" < mate."position") AS ahead,
    count(*) FILTER (WHERE me."position" > mate."position") AS behind,
    count(*) FILTER (WHERE me."position" < mate."position")::numeric / count(*)::numeric AS h2h_rate,
    round(avg(mate."position" - me."position"), 3) AS avg_position_delta,
    round(avg(me."position"), 3) AS my_avg_position,
    round(avg(mate."position"), 3) AS teammate_avg_position,
    min(s.year) AS first_season,
    max(s.year) AS last_season,
    count(*) >= 5 AS comparable,
    min(d1.slug) AS driver_slug,
    min(d2.slug) AS teammate_slug
   FROM results me
     JOIN results mate ON mate.race_id = me.race_id AND mate.constructor_id = me.constructor_id AND mate.driver_id <> me.driver_id
     JOIN races ra ON ra.id = me.race_id
     JOIN seasons s ON s.id = ra.season_id
     JOIN drivers d1 ON d1.id = me.driver_id
     JOIN drivers d2 ON d2.id = mate.driver_id
     JOIN constructors co ON co.id = me.constructor_id
  GROUP BY me.driver_id, d1.display_name, mate.driver_id, d2.display_name, me.constructor_id, co.constructor_name;
