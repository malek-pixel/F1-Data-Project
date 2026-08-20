-- Views default to SECURITY DEFINER, which makes them enforce the *creator's*
-- permissions and RLS rather than the querying user's. For a public analytical
-- API that is the wrong default: a view must never become a way around the
-- policies on its base tables.
--
-- security_invoker = true makes each view run with the caller's rights, so RLS
-- on results/drivers/etc. applies exactly as it does to a direct select.
ALTER VIEW v_race_results                    SET (security_invoker = true);
ALTER VIEW v_driver_career_stats             SET (security_invoker = true);
ALTER VIEW v_driver_season_stats             SET (security_invoker = true);
ALTER VIEW v_driver_circuit_stats            SET (security_invoker = true);
ALTER VIEW v_constructor_career_stats        SET (security_invoker = true);
ALTER VIEW v_constructor_season_stats        SET (security_invoker = true);
ALTER VIEW v_constructor_driver_contribution SET (security_invoker = true);
ALTER VIEW v_teammate_comparisons            SET (security_invoker = true);
ALTER VIEW v_season_stats                    SET (security_invoker = true);
ALTER VIEW v_circuit_stats                   SET (security_invoker = true);
ALTER VIEW v_records                         SET (security_invoker = true);
