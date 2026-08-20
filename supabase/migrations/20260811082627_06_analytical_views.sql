-- ============================================================================
-- Analytical layer.
--
-- Views, not tables: these are derived from results and must never become a
-- second source of truth that can drift. They are also cheap -- the dataset is
-- 10,550 rows, so materialisation would add refresh complexity for no
-- measurable gain. Revisit only if a measurement says otherwise.
--
-- Definitions mirror backend/app/analytics.py exactly. Divergence between the
-- two is a bug; the reconciliation query in docs/database.md proves they agree.
--
-- NAMING: every position-derived metric says "classified", never "finishing".
-- The source has no status column, so retirements are ranked, not flagged.
-- ============================================================================

-- Row-level view joining results to readable entity names.
CREATE VIEW v_race_results AS
SELECT r.id AS result_id, ra.id AS race_id, s.year AS season, ra.round,
       ra.race_name, ra.race_date, ci.id AS circuit_id, ci.circuit_name, ci.circuit_key,
       d.id AS driver_id, d.display_name AS driver_name, d.driver_key,
       co.id AS constructor_id, co.constructor_name, co.constructor_key,
       r.position
FROM results r
JOIN races ra        ON ra.id = r.race_id
JOIN seasons s       ON s.id  = ra.season_id
JOIN circuits ci     ON ci.id = ra.circuit_id
JOIN drivers d       ON d.id  = r.driver_id
JOIN constructors co ON co.id = r.constructor_id;

-- ---------------------------------------------------------------- drivers
CREATE VIEW v_driver_career_stats AS
SELECT d.id AS driver_id, d.driver_key, d.display_name,
       count(*)                                                    AS entries,
       count(*) FILTER (WHERE r.position = 1)                      AS wins,
       count(*) FILTER (WHERE r.position <= 3)                     AS podiums,
       count(*) FILTER (WHERE r.position <= 5)                     AS top5,
       count(*) FILTER (WHERE r.position <= 10)                    AS top10,
       -- Rates are NULL, never 0, when there is nothing to divide by.
       (count(*) FILTER (WHERE r.position = 1))::numeric  / nullif(count(*),0) AS win_rate,
       (count(*) FILTER (WHERE r.position <= 3))::numeric / nullif(count(*),0) AS podium_rate,
       (count(*) FILTER (WHERE r.position <= 5))::numeric / nullif(count(*),0) AS top5_rate,
       (count(*) FILTER (WHERE r.position <= 10))::numeric/ nullif(count(*),0) AS top10_rate,
       round(avg(r.position)::numeric, 3)                          AS avg_classified_position,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.position)     AS median_classified_position,
       CASE WHEN count(*) >= 5 THEN round(stddev_samp(r.position)::numeric, 3) END AS position_stdev,
       min(r.position)                                             AS best_classified_position,
       min(s.year)                                                 AS first_season,
       max(s.year)                                                 AS last_season,
       count(*) >= 10                                              AS rates_reliable
FROM drivers d
JOIN results r ON r.driver_id = d.id
JOIN races ra  ON ra.id = r.race_id
JOIN seasons s ON s.id = ra.season_id
GROUP BY d.id;
COMMENT ON VIEW v_driver_career_stats IS
    'rates_reliable is false below 10 entries: the rate is still returned so a '
    'small sample is visible rather than hidden.';

CREATE VIEW v_driver_season_stats AS
SELECT d.id AS driver_id, d.display_name, s.year AS season,
       count(*)                                   AS entries,
       count(*) FILTER (WHERE r.position = 1)     AS wins,
       count(*) FILTER (WHERE r.position <= 3)    AS podiums,
       count(*) FILTER (WHERE r.position <= 10)   AS top10,
       (count(*) FILTER (WHERE r.position = 1))::numeric / nullif(count(*),0) AS win_rate,
       round(avg(r.position)::numeric, 3)         AS avg_classified_position,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.position) AS median_classified_position,
       min(r.position)                            AS best_classified_position
FROM drivers d
JOIN results r ON r.driver_id = d.id
JOIN races ra  ON ra.id = r.race_id
JOIN seasons s ON s.id = ra.season_id
GROUP BY d.id, s.year;

CREATE VIEW v_driver_circuit_stats AS
SELECT d.id AS driver_id, d.display_name, ci.id AS circuit_id, ci.circuit_name,
       count(*)                                 AS appearances,
       count(*) FILTER (WHERE r.position = 1)   AS wins,
       count(*) FILTER (WHERE r.position <= 3)  AS podiums,
       round(avg(r.position)::numeric, 3)       AS avg_classified_position,
       min(r.position)                          AS best_classified_position,
       -- Measured against the driver's own career norm, so it needs no model
       -- of car strength. Positive = better here than usual.
       round((SELECT avg(r2.position) FROM results r2 WHERE r2.driver_id = d.id)::numeric
             - avg(r.position)::numeric, 3)     AS delta_vs_career,
       count(*) >= 5                            AS meets_specialism_threshold
FROM drivers d
JOIN results r  ON r.driver_id = d.id
JOIN races ra   ON ra.id = r.race_id
JOIN circuits ci ON ci.id = ra.circuit_id
GROUP BY d.id, ci.id;

-- ----------------------------------------------------------- constructors
-- NOTE: a constructor fields two cars, so entries are per-car classifications,
-- not per-race. Counting races would double-count; that is deliberate and the
-- column is named `entries` for exactly that reason.
CREATE VIEW v_constructor_career_stats AS
SELECT co.id AS constructor_id, co.constructor_key, co.constructor_name,
       count(*)                                                     AS entries,
       count(DISTINCT r.race_id)                                    AS races_contested,
       count(*) FILTER (WHERE r.position = 1)                       AS wins,
       count(*) FILTER (WHERE r.position <= 3)                      AS podiums,
       count(*) FILTER (WHERE r.position <= 10)                     AS top10,
       (count(*) FILTER (WHERE r.position = 1))::numeric  / nullif(count(*),0) AS win_rate,
       (count(*) FILTER (WHERE r.position <= 3))::numeric / nullif(count(*),0) AS podium_rate,
       round(avg(r.position)::numeric, 3)                           AS avg_classified_position,
       min(r.position)                                              AS best_classified_position,
       min(s.year) AS first_season, max(s.year) AS last_season
FROM constructors co
JOIN results r ON r.constructor_id = co.id
JOIN races ra  ON ra.id = r.race_id
JOIN seasons s ON s.id = ra.season_id
GROUP BY co.id;

CREATE VIEW v_constructor_season_stats AS
SELECT co.id AS constructor_id, co.constructor_name, s.year AS season,
       count(*)                                  AS entries,
       count(DISTINCT r.race_id)                 AS races_contested,
       count(*) FILTER (WHERE r.position = 1)    AS wins,
       count(*) FILTER (WHERE r.position <= 3)   AS podiums,
       round(avg(r.position)::numeric, 3)        AS avg_classified_position
FROM constructors co
JOIN results r ON r.constructor_id = co.id
JOIN races ra  ON ra.id = r.race_id
JOIN seasons s ON s.id = ra.season_id
GROUP BY co.id, s.year;

-- Driver contribution: share of the team's own results.
-- Share of POINTS is impossible -- the source has no points column.
CREATE VIEW v_constructor_driver_contribution AS
SELECT co.id AS constructor_id, co.constructor_name,
       d.id AS driver_id, d.display_name AS driver_name,
       count(*) AS entries,
       count(*) FILTER (WHERE r.position = 1)  AS wins,
       count(*) FILTER (WHERE r.position <= 3) AS podiums,
       count(*)::numeric / sum(count(*)) OVER (PARTITION BY co.id) AS entry_share,
       nullif(count(*) FILTER (WHERE r.position = 1), 0)::numeric
         / nullif(sum(count(*) FILTER (WHERE r.position = 1)) OVER (PARTITION BY co.id), 0) AS win_share
FROM constructors co
JOIN results r ON r.constructor_id = co.id
JOIN drivers d ON d.id = r.driver_id
GROUP BY co.id, d.id;

-- -------------------------------------------------------------- teammates
-- Two drivers are teammates in a race when both have a result row for the SAME
-- race and the SAME constructor. Only those races are counted, which is what
-- removes the distortion from unequal season lengths and mid-season swaps.
--
-- LIMITATION: with no finishing status, a mechanical retirement counts as a
-- head-to-head loss. This measures who was CLASSIFIED ahead, not who was faster.
CREATE VIEW v_teammate_comparisons AS
SELECT me.driver_id,
       d1.display_name AS driver_name,
       mate.driver_id  AS teammate_id,
       d2.display_name AS teammate_name,
       me.constructor_id,
       co.constructor_name,
       count(*)                                                  AS shared_races,
       count(*) FILTER (WHERE me.position < mate.position)       AS ahead,
       count(*) FILTER (WHERE me.position > mate.position)       AS behind,
       (count(*) FILTER (WHERE me.position < mate.position))::numeric / count(*) AS h2h_rate,
       round(avg(mate.position - me.position)::numeric, 3)       AS avg_position_delta,
       round(avg(me.position)::numeric, 3)                       AS my_avg_position,
       round(avg(mate.position)::numeric, 3)                     AS teammate_avg_position,
       min(s.year) AS first_season, max(s.year) AS last_season,
       count(*) >= 5                                             AS comparable
FROM results me
JOIN results mate ON mate.race_id = me.race_id
                 AND mate.constructor_id = me.constructor_id
                 AND mate.driver_id <> me.driver_id
JOIN races ra        ON ra.id = me.race_id
JOIN seasons s       ON s.id  = ra.season_id
JOIN drivers d1      ON d1.id = me.driver_id
JOIN drivers d2      ON d2.id = mate.driver_id
JOIN constructors co ON co.id = me.constructor_id
GROUP BY me.driver_id, d1.display_name, mate.driver_id, d2.display_name,
         me.constructor_id, co.constructor_name;

-- --------------------------------------------------------------- seasons
CREATE VIEW v_season_stats AS
SELECT s.year AS season,
       count(DISTINCT ra.id)                                   AS races,
       count(r.id)                                             AS entries,
       count(DISTINCT r.driver_id)                             AS drivers,
       count(DISTINCT r.constructor_id)                        AS constructors,
       count(DISTINCT r.driver_id) FILTER (WHERE r.position = 1)      AS distinct_race_winners,
       count(DISTINCT r.constructor_id) FILTER (WHERE r.position = 1) AS distinct_winning_constructors,
       round(avg(r.position)::numeric, 3)                      AS avg_classified_position
FROM seasons s
JOIN races ra ON ra.season_id = s.id
LEFT JOIN results r ON r.race_id = ra.id
GROUP BY s.year;
COMMENT ON VIEW v_season_stats IS
    'NOT championship standings. The source has no points column, so official '
    'season order cannot be reproduced; consumers rank by wins and must say so.';

-- --------------------------------------------------------------- circuits
CREATE VIEW v_circuit_stats AS
SELECT ci.id AS circuit_id, ci.circuit_key, ci.circuit_name, ci.country,
       count(DISTINCT ra.id)                                          AS races,
       count(r.id)                                                    AS entries,
       count(DISTINCT r.driver_id) FILTER (WHERE r.position = 1)      AS distinct_winners,
       round(avg(r.position)::numeric, 3)                             AS avg_classified_position,
       min(s.year) AS first_season, max(s.year) AS last_season,
       ci.svg_asset IS NOT NULL                                       AS has_map
FROM circuits ci
JOIN races ra  ON ra.circuit_id = ci.id
JOIN seasons s ON s.id = ra.season_id
LEFT JOIN results r ON r.race_id = ra.id
GROUP BY ci.id;

-- ---------------------------------------------------------------- records
-- Calculated, never hardcoded. Rate records apply the minimum-sample filter so
-- a one-race driver cannot top a rate table.
CREATE VIEW v_records AS
SELECT * FROM (
  SELECT 'Most wins (driver)' AS record, display_name AS entity, wins::numeric AS value,
         NULL::text AS context, 'Race wins across the dataset window.' AS methodology,
         NULL::int AS min_sample
  FROM v_driver_career_stats ORDER BY wins DESC, podiums DESC LIMIT 1
) a
UNION ALL SELECT * FROM (
  SELECT 'Most podiums (driver)', display_name, podiums::numeric, NULL,
         'Classified P1-P3.', NULL::int
  FROM v_driver_career_stats ORDER BY podiums DESC LIMIT 1
) b
UNION ALL SELECT * FROM (
  SELECT 'Most entries (driver)', display_name, entries::numeric, NULL,
         'Race classifications, including retirements.', NULL::int
  FROM v_driver_career_stats ORDER BY entries DESC LIMIT 1
) c
UNION ALL SELECT * FROM (
  SELECT 'Highest win rate (driver)', display_name, round(win_rate, 4), NULL,
         'wins / entries, minimum 10 entries.', 10
  FROM v_driver_career_stats WHERE rates_reliable ORDER BY win_rate DESC LIMIT 1
) d
UNION ALL SELECT * FROM (
  SELECT 'Best average classified position (driver)', display_name, avg_classified_position, NULL,
         'Mean classification incl. retirements, minimum 10 entries.', 10
  FROM v_driver_career_stats WHERE rates_reliable ORDER BY avg_classified_position ASC LIMIT 1
) e
UNION ALL SELECT * FROM (
  SELECT 'Most wins (constructor)', constructor_name, wins::numeric, NULL,
         'Race wins across the dataset window.', NULL::int
  FROM v_constructor_career_stats ORDER BY wins DESC LIMIT 1
) f
UNION ALL SELECT * FROM (
  SELECT 'Most wins in a season (driver)', display_name, wins::numeric, season::text,
         'Wins within one season. Season lengths vary 16-24 races, so totals are not era-normalised.', NULL::int
  FROM v_driver_season_stats ORDER BY wins DESC, season LIMIT 1
) g
UNION ALL SELECT * FROM (
  SELECT 'Most wins at one circuit (driver)', display_name, wins::numeric, circuit_name,
         'Wins at a single circuit. Circuits appear in different numbers of seasons.', NULL::int
  FROM v_driver_circuit_stats ORDER BY wins DESC, display_name LIMIT 1
) h;

-- Views inherit RLS from their base tables when created by a non-superuser,
-- but make read intent explicit for the API roles.
GRANT SELECT ON v_race_results, v_driver_career_stats, v_driver_season_stats,
                v_driver_circuit_stats, v_constructor_career_stats,
                v_constructor_season_stats, v_constructor_driver_contribution,
                v_teammate_comparisons, v_season_stats, v_circuit_stats, v_records
      TO anon, authenticated;
