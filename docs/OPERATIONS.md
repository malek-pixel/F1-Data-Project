# Operations: recovery, migrations, deployment, monitoring

Written during the production-readiness audit. It answers the questions that
only get asked once something has gone wrong, and it is deliberately specific
about what this project does *not* have.

---

## 1. Where the data actually lives

Three stores, and it matters which one you are recovering.

| Store | What it holds | Authoritative? | Rebuildable? |
|---|---|---|---|
| `data/*.csv` | The ingested source extracts, **committed to git** (~36 MB) | **Yes — this is the source of truth in the repo** | No. Re-fetched from Jolpica / FastF1. |
| `data/f1.db` | SQLite build artefact | No | **Yes, fully.** `python -m backend.etl.build` |
| Supabase Postgres | The same data, materialised for the hosted API | No | Yes, from the CSVs via `backend/etl/supabase_import.py` |

The consequence worth internalising: **`data/f1.db` and the Supabase tables are
both derived.** Neither is a thing you need to back up. Losing either costs you
a rebuild, not data. The irreplaceable artefacts are the committed CSVs and the
migration history — both in git.

### Verified reproducibility

`data/f1.db` was rebuilt from scratch three times during the audit and produced
a **byte-identical** database each time (`md5 5f45e8dc…`), with all 552,138 lap
timings and 211,257 practice laps intact, and 381/381 tests passing on the
fresh build. The build is idempotent: it upserts, so running it against an
existing database does not destroy the separately-fetched tables.

```bash
python -m backend.etl.build
```

```bash
python -m backend.etl.audit
```

---

## 2. Recovery procedures

### The SQLite database is corrupt or missing

```bash
python -m backend.etl.build && python -m backend.etl.audit
```

Takes a couple of minutes. No network needed — every source CSV is committed.

### A Supabase table was damaged

Re-run the ingestion for that table. The importer upserts on the natural key,
so it is safe to re-run and converges on the committed CSVs:

```bash
python -m backend.etl.supabase_import
```

(Needs `SUPABASE_DB_URL` in the environment — see §5.)

Then confirm the two stores agree — this is what the parity suite is for:

```bash
python -m pytest backend/tests/test_store_parity.py backend/tests/test_backend_parity.py -q
```

### A bad migration was applied

There is **no automated rollback**, and this is the sharpest operational edge
in the project. Before applying anything destructive:

1. Take a Supabase point-in-time restore point (Dashboard → Database → Backups).
   On the free tier PITR is not available — take a manual `pg_dump` first.
2. Apply the migration.
3. Run the checksum verifier and the parity tests above.

If a migration has already caused damage: restore from the Supabase backup, then
re-run the ingestion. Because every table is derived from committed CSVs, a
restore-then-reimport always terminates in a known-good state.

**Nothing in the database is unrecoverable — but the RLS policies and grants
live only in the migration files, so restoring a snapshot without re-applying
migrations 02, 05 and 07 can leave the database readable *and writable*. Verify
grants after any restore** (see §4).

### Verifying a restore

```bash
python supabase/verify_migrations.py && python -m backend.etl.audit && python -m pytest backend/tests -q
```

---

## 3. Migrations

24 migrations in `supabase/migrations/`, checksummed in `CHECKSUMS.md5` and
verified by `supabase/verify_migrations.py`, which passes today. They are
ordered by filename timestamp and must be applied in that order — several
depend on earlier ones (13 rewrites views created in 06; 17 and 22–23 rewrite
them again).

Rules that have held so far and should keep holding:

* **Never edit an applied migration.** The checksum file will catch it, and the
  next person to rebuild will get a different schema than the one recorded.
  Write a new migration instead.
* **New tables need RLS in the same migration.** Every table-creating migration
  in this repository also enables RLS and grants `select` to `anon`. If you add
  a table without it, the table is readable *and writable* by every public key.
  This was verified empirically, not just read (§4).
* Destructive changes (`drop`, `alter … type`, `delete`) need a restore point
  taken first. There is no down-migration.

---

## 4. The access model, and how to re-verify it

Intended model: **the public is read-only.** Writes happen only from the
ingestion pipeline, which connects with `SUPABASE_DB_URL` (server-side, holds
the database password) and never through a public key.

Enforced twice, on purpose:

* RLS: a `select` policy for `anon` and `authenticated`, and **no**
  insert/update/delete policy for anyone.
* Grants: `revoke insert, update, delete, truncate … from anon, authenticated`,
  plus matching default privileges.

Belt and braces, because a policy that exists can be widened by accident and an
absent policy cannot.

Re-verify after any restore or policy change — this was run during the audit
against all 21 tables and is the check that actually proves the model:

```bash
python -m pytest backend/tests/test_supabase.py -q
```

Expected: `select` succeeds on the public tables and is denied on
`staging_results`; `insert`, `update` and `delete` all return
`42501 permission denied`. The suite skips itself when the `SUPABASE_*`
variables are absent.

---

## 5. Deployment

The frontend and API are separate deployables. The browser **never talks to
Supabase directly** — every request goes through the API — so no Supabase key
of any kind belongs in the frontend bundle. This was confirmed against the
built output during the audit.

### Environment variables

| Name | Where | Secret? | Required |
|---|---|---|---|
| `SUPABASE_URL` | API | No — a public URL | Only when `F1_BACKEND=supabase` |
| `SUPABASE_ANON_KEY` | API | No — RLS-limited to `select` | Only when `F1_BACKEND=supabase` |
| `SUPABASE_DB_URL` | Ingestion only | **Yes — database password** | Only to ingest |
| `SUPABASE_SERVICE_ROLE_KEY` | Unused today | **Yes — bypasses RLS** | No |
| `F1_ALLOWED_ORIGINS` | API | No | **Yes in production** |
| `F1_BACKEND` | API | No | Defaults to `sqlite` |

`.env` is gitignored and untracked; `.env.example` holds placeholders only. Git
history was scanned during the audit and contains no real credential.

### Must be configured before going live

1. **`F1_ALLOWED_ORIGINS` → the real domain.** It defaults to
   `http://localhost:5173`, which will reject the deployed frontend. Never
   wildcard it; the middleware allows `GET` only.
2. **Serve the API and the frontend under HTTPS.** The client calls a relative
   `/api`, so a same-origin deploy needs no CORS configuration at all — this is
   the recommended shape.
3. **Choose the backend.** `F1_BACKEND=sqlite` ships `data/f1.db` with the API
   (simple, fast, read-only, no network dependency). `F1_BACKEND=supabase`
   needs the two Supabase variables. The API refuses to start on a
   misconfigured backend rather than failing later as an intermittent 503.
4. **Image rights are not cleared.** 266 car photos, 129 driver portraits and
   the team logos are third-party. This is a legal blocker for a public
   deployment, not a technical one. See `docs/CAR_PHOTOS.md`.

### Build

```bash
cd frontend && npm ci && npm run build
```

```bash
uvicorn backend.app.main:app --port 8000
```

---

## 6. Monitoring — what exists, and what does not

**There is no monitoring, error reporting or alerting in this project today.**
Nothing is silently collecting errors; if the deployed app breaks, no one is
told. That is a statement of the current state, not a plan.

What already exists to build on:

* `/api/health` returns liveness *and* dataset coverage. Good uptime-check target.
* Every handled failure returns `{"detail": …}` with a real status — `503` for a
  data-store outage, `501` for a capability the active backend lacks, `422` for
  invalid input. Server-side the real exception is logged; the client only ever
  sees the safe message.

The minimum worth adding before a public launch, in priority order:

1. **Uptime check on `/api/health`** — catches the whole class of "it's down".
2. **Frontend error reporting** (Sentry or equivalent) — the SPA currently
   turns a failed request into an error state with no signal to anyone.
3. **API 5xx rate and p95 latency.** Slowest endpoints measured during the audit
   were `dataset/summary` (~400–500 ms) and `records` (~340 ms); everything else
   was under 200 ms.

Not recommended: building custom infrastructure for any of this. Use the
platform's.

---

## 7. Routine maintenance

| Task | When | Command |
|---|---|---|
| Re-run integrity audit | After any ingestion | `python -m backend.etl.audit` |
| Cross-validate against Jolpica | After ingestion, needs network | `python -m backend.etl.crossvalidate` |
| Verify migration checksums | After any schema change | `python supabase/verify_migrations.py` |
| Backend tests | Before every deploy | `python -m pytest backend/tests -q` |
| Frontend tests | Before every deploy | `cd frontend && npm test` |
| Dependency advisories | Monthly | `cd frontend && npm audit --omit=dev` |

CI (`.github/workflows/ci.yml`) runs the build, both test suites, the data
audit, the migration checksums and the production build on every push.
