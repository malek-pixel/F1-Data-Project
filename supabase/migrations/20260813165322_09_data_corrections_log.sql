-- ============================================================================
-- Corrections log.
--
-- When a stored value turns out to be wrong, overwriting it destroys the only
-- evidence that it was ever wrong. That matters most for historical data,
-- where "this number changed" is itself a fact a reader may need.
--
-- One row per deliberate correction: what it was, what it became, why, on what
-- evidence, and who decided. Append-only by construction -- no UPDATE or
-- DELETE policy exists for any role reachable from the application.
--
-- This is NOT a generic row-version history. Bulk re-imports are idempotent
-- upserts and are already provable from datasets.checksum; recording every
-- upsert here would bury the deliberate corrections in noise. Only a decision
-- to change a value belongs in this table.
-- ============================================================================

create table data_corrections (
    id              bigint generated always as identity primary key,
    -- What was corrected. Free text rather than an FK: the target may be a
    -- column, a table, or a row that a later migration removes, and a dangling
    -- FK would make the log itself undeletable or lossy.
    target_table    text        not null,
    target_column   text,
    target_ref      text,
    -- NULL previous_value means the field was empty, not that it was unknown.
    previous_value  text,
    corrected_value text,
    -- Why this was changed, and on what evidence. NOT NULL on purpose: a
    -- correction without a stated reason is indistinguishable from tampering.
    reason          text        not null,
    evidence        text        not null,
    source_id       bigint      references data_sources(id),
    corrected_by    text        not null,
    corrected_at    timestamptz not null default now()
);

comment on table data_corrections is
    'Append-only record of deliberate data corrections. Evidence and reason '
    'are NOT NULL: a correction without stated grounds is indistinguishable '
    'from tampering.';
comment on column data_corrections.previous_value is
    'NULL means the field was genuinely empty before the correction, never '
    'that the prior value is unknown.';

create index idx_corrections_target on data_corrections(target_table, corrected_at desc);

alter table data_corrections enable row level security;

-- Public read: the corrections history is part of the published provenance
-- story. Deliberately no INSERT/UPDATE/DELETE policy, so the log is
-- append-only from the server side and immutable from every public key.
create policy public_read_data_corrections on data_corrections
    for select to anon, authenticated using (true);
revoke insert, update, delete, truncate on data_corrections from anon, authenticated;

-- Seed with the correction actually made on 2026-08-13, so the table starts
-- as a true record rather than an empty promise.
insert into data_corrections
    (target_table, target_column, target_ref, previous_value, corrected_value,
     reason, evidence, source_id, corrected_by)
select
    'datasets', 'checksum', 'dataset_key=ergast_results, version=2025.1',
    null,
    '63ec510c83e26576a02331ee067cb5f705f1c330e64325fd7b540b6c16646f7b',
    'checksum was NULL, so the column comment''s guarantee -- "SHA-256 of the '
    'source file, so an import can prove which bytes it read" -- was not being '
    'met. The stored row predated the import code that writes it.',
    'Not backfilled on a matching row count. All 10,550 rows were fingerprinted '
    'on both sides (md5 of the sorted seven-column projection) and agree '
    'exactly: e4231564629c4abd8110daab82a60a0b. The same SHA-256 was already '
    'present independently in the SQLite build''s build_meta table.',
    id,
    'backend audit, 2026-08-13'
from data_sources where source_key = 'ergast_csv';