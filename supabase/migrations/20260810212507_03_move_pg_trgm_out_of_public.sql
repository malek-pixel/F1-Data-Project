-- pg_trgm in `public` puts extension functions in the same namespace as
-- application objects and in the default search_path of every role. Move it to
-- a dedicated schema; the trigram indexes are rebuilt against the moved
-- operator classes.

drop index if exists idx_drivers_name_trgm;
drop index if exists idx_constructors_name_trgm;
drop index if exists idx_circuits_name_trgm;

create schema if not exists extensions;
grant usage on schema extensions to anon, authenticated, service_role;

drop extension if exists pg_trgm;
create extension pg_trgm with schema extensions;

create index idx_drivers_name_trgm
    on drivers using gin (display_name extensions.gin_trgm_ops);
create index idx_constructors_name_trgm
    on constructors using gin (constructor_name extensions.gin_trgm_ops);
create index idx_circuits_name_trgm
    on circuits using gin (circuit_name extensions.gin_trgm_ops);
