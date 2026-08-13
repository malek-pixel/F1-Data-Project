-- Revoke the load-only grant. Staging returns to server-side-only: no policy,
-- no grant, not readable or writable by anon.
DROP POLICY IF EXISTS tmp_staging_load ON staging_results;
DROP POLICY IF EXISTS tmp_staging_read ON staging_results;
REVOKE INSERT ON staging_results FROM anon;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon;

-- Drop the abandoned transport scaffolding from the earlier approach.
DROP TABLE IF EXISTS _load_races;
DROP TABLE IF EXISTS _load_races2;
DROP TABLE IF EXISTS _load_names;
