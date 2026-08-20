-- ============================================================================
-- Row Level Security
--
-- MODEL: this is a public analytical product over public historical F1 data.
--   * anon + authenticated  -> SELECT only
--   * INSERT/UPDATE/DELETE  -> no policy for anyone, so the ingestion pipeline
--                              must use the service role (server-side only).
--
-- There is deliberately no write policy rather than a restrictive one: a
-- policy that exists can be widened by accident, an absent policy cannot.
-- RLS is not bypassed by the service role key, which is why ingestion uses it
-- and why that key never reaches the browser.
-- ============================================================================

do $$
declare t text;
begin
    foreach t in array array[
        'data_sources','datasets','seasons','circuits','drivers','constructors',
        'cars','races','results','driver_constructor_seasons',
        'data_quality_checks','metric_definitions'
    ]
    loop
        execute format('alter table public.%I enable row level security', t);
        -- Read-only public access. No USING clause restriction: every row of
        -- this dataset is public historical record.
        execute format(
            'create policy %I on public.%I for select to anon, authenticated using (true)',
            'public_read_' || t, t);
    end loop;
end $$;

-- Explicitly deny writes to the public roles at the grant level too, so a
-- future policy mistake still cannot open them.
revoke insert, update, delete, truncate on all tables in schema public from anon, authenticated;
alter default privileges in schema public
    revoke insert, update, delete on tables from anon, authenticated;
