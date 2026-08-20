-- ---------------------------------------------------------------------------
-- 24. The fastest-lap enrichment columns, which Postgres never received.
--
-- WHY THIS EXISTS
-- ---------------
-- The SQLite build carries fastest_lap_rank / _number / _time / _speed on
-- `results` -- 8,725 rows of it, covering 2004-2025. The Postgres `results`
-- table had none of the four columns. The two stores were therefore not two
-- materialisations of the same data at all: one of them was missing a
-- dataset, and nothing detected it because /api/races/{id} never dispatched
-- to Supabase, so no comparison of that payload had ever run.
--
-- This adds the columns. `backend/etl/backfill_fastest_lap.py` loads the
-- values, keyed on (season, round, driver slug) rather than on ids, because
-- result ids come from a different sequence in each store.
--
-- NULL means the source publishes no fastest lap for that row -- every row
-- before 2004, and the rows a partially enriched build has not reached. It is
-- never zero: "no fastest lap recorded" and "a fastest lap of zero" are
-- different statements, and only one of them is possible.
-- ---------------------------------------------------------------------------

alter table results add column if not exists fastest_lap_rank   int;
alter table results add column if not exists fastest_lap_number int;
alter table results add column if not exists fastest_lap_time   text;
alter table results add column if not exists fastest_lap_speed  numeric(7,3);

comment on column results.fastest_lap_rank is
    'Rank of this driver''s fastest lap within the race, as published. 1 is '
    'the fastest-lap award. NOT the same as the quickest time in lap_times: '
    'the award applies eligibility rules a raw minimum does not.';
comment on column results.fastest_lap_speed is
    'Average speed of that lap in km/h. NULL where the source omits it, which '
    'is 487 of the 8,725 enriched rows -- never estimated from the lap time.';

-- Partial index: the award lookup is `where fastest_lap_rank = 1`, one row per
-- race, so indexing only the ranked rows keeps it small.
create index if not exists results_fastest_lap_award_idx
    on results (race_id) where fastest_lap_rank = 1;


-- ---------------------------------------------------------------------------
-- Nationality on the career-stats views.
--
-- All 129 drivers and every constructor carry a nationality, and the driver
-- and constructor DETAIL pages already render it. The browsable library did
-- not, because the listing is built from the career-stats views and those
-- views had no such column -- so the card showed "NAT —" under a tooltip
-- saying nationality "is not in results.csv", beside a database that has it
-- for every row.
--
-- Appended, because CREATE OR REPLACE VIEW may only add columns at the end.
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
    d.display_name collate "C" AS sort_name,
    d.nationality
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
    co.constructor_name collate "C" AS sort_name,
    co.nationality
   FROM constructors co
     JOIN results r ON r.constructor_id = co.id
     JOIN races ra ON ra.id = r.race_id
     JOIN seasons s ON s.id = ra.season_id
  GROUP BY co.id;

grant select on v_driver_career_stats      to anon, authenticated;
grant select on v_constructor_career_stats to anon, authenticated;
