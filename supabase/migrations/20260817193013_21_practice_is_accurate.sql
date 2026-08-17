-- ============================================================================
-- practice_laps.is_accurate
--
-- The source's own judgement that a lap's timing is self-consistent. Added
-- after a test found sector times failing to reconstruct the lap -- one lap
-- out by thirty seconds -- and the flag turned out to separate the two cases
-- exactly: across a full session, zero mismatches among accurate laps and
-- every mismatch inaccurate.
--
-- Inaccurate laps are KEPT. They were driven, and dropping them would shrink
-- every lap count while hiding why. The flag lets a consumer exclude them
-- deliberately, and lets an integrity check assert the sector invariant on
-- the laps where it actually holds.
--
-- SQLite carried this column first; Postgres without it meant the two stores
-- were not structurally equal, which the parity suite compares values through
-- and would not have caught on its own.
-- ============================================================================

alter table practice_laps add column is_accurate boolean not null default false;

comment on column practice_laps.is_accurate is
    'Source judgement that the lap timing is self-consistent. Sector times '
    'reconstruct the lap only when true; inaccurate laps are kept and flagged.';
