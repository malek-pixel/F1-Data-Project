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

That sequence now also proves the rebuild is **deterministic**, not merely
repeatable. `backend/tests/test_reproducibility.py` rebuilds the database from
the committed CSVs into a throwaway file and compares it table by table,
ordered by every column, against the one being served. It exists because a
pipeline can run twice without erroring while assigning different surrogate
ids each time — which would leave the database unrestorable in the only sense
that matters, since `/drivers/65` would then point at a different driver after
a rebuild. The build iterates over sets of names and Python randomises string
hashing per process, so the risk was real rather than hypothetical. Verified:
every table identical across two builds in two processes.

### What is still NOT proven

**No restore has ever been performed.** Everything above verifies a database
*after* a restore; nothing here has exercised getting one back. PITR is
unavailable on the current Supabase tier, so the recovery path is a manual
`pg_dump` that has never been taken, followed by a re-import that has never
been run against a fresh project.

A backup that has never been restored is not proven recoverable, and no amount
of documentation changes that. The drill, when someone runs it, is:

1. Create a scratch Supabase project (free tier is sufficient).
2. Apply all 24 migrations in order, then `python supabase/verify_migrations.py`.
3. `SUPABASE_DB_URL=<scratch> python -m backend.etl.supabase_import`.
4. Point `SUPABASE_URL` / `SUPABASE_ANON_KEY` at the scratch project and run
   `python -m pytest backend/tests -q`. The parity suites compare it against
   SQLite row for row; a clean run means the rebuilt project is equivalent to
   the real one.
5. Record the date and the result here, and delete the scratch project.

Until step 5 has a date next to it, treat recovery as reasoned, not
demonstrated.

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

### Last verified

**2026-08-21 — run against the live project with credentials present, and
passed.** This matters because the suites above are skip-by-default, and a
skipped test reports the same green as a passing one. The distinction that had
been outstanding was *verified-good* versus *unverified*; it is now the former,
on this date, with these results:

| Check | Result |
|---|---|
| `supabase/verify_migrations.py` | 24/24 match the SQL recorded as applied |
| `test_supabase.py` — RLS, grants, row counts, analytics | 24 passed, 0 skipped |
| `test_store_parity.py` + `test_backend_parity.py` — row-level SQLite vs Postgres | 27 passed |
| `test_api_payload_parity.py` — 77 request paths, response for response | 83 passed |

Re-run and re-date this table after any migration, ingestion or restore. **CI
does not do it for you** — see the note in §7 — so if this date is old, the
answer to "is Supabase still in parity" is *unknown*, not *yes*.

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
| `F1_LOG_FORMAT` | API | No | `text` (local) / set `json` in production |
| `F1_LOG_LEVEL` | API | No | Defaults to `INFO` |
| `F1_SLOW_REQUEST_MS` | API | No | Defaults to `1000` |
| `F1_SENTRY_DSN` | API | No — a DSN is a write-only ingest URL | No; off when unset |
| `F1_ENVIRONMENT` | API | No | Defaults to `production`; only read when a DSN is set |

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
4. **Image provenance is unrecorded.** 266 car photos, 129 driver portraits,
   35 team logos and 25 circuit outlines are third-party, and nothing in the
   repository records where any of them came from. Noted so the position is
   explicit rather than forgotten; every image has a graceful labelled
   fallback, so removing them is a layout-safe change if that is ever wanted.
   See `docs/CAR_PHOTOS.md`.

### Build

```bash
cd frontend && npm ci && npm run build
```

```bash
uvicorn backend.app.main:app --port 8000
```

---

## 6. Monitoring — what exists, and what does not

The application is now **instrumented**. Whether anyone is **notified** is a
deployment decision, and the difference between those two sentences is the
whole of this section. Read the last subsection before assuming you are
covered.

### What the API emits

`backend/app/observability.py`, wired in `main.py`:

* **A request id on every request.** Taken from an inbound `X-Request-ID` when
  a proxy set one, minted otherwise. Echoed on the response, attached to every
  log line the request produces, and returned in the body of every error
  response as `request_id` — so a reader who says "it broke, id `a3f9…`" turns
  an afternoon of guessing into one `grep`.

  The inbound header is length-bounded and alphabet-restricted, and anything
  failing either check is **replaced rather than sanitised**. It is
  attacker-controlled and lands in both a log line and a response header;
  stripping a newline from `abc\nERROR forged entry` still writes the
  attacker's text into your log.

  One asymmetry worth knowing: the **header** is on every response without
  exception, but `request_id` appears in the response **body** only for the
  four handled failures (`503` store outage, `503` Supabase outage, `501`
  missing capability, `500` unhandled). A routine `404` or `422` is raised as
  an `HTTPException` and rendered by FastAPI's own handler, whose body is
  `{"detail": …}` and nothing else. That was left alone deliberately — those
  bodies are an established contract the frontend and the API tests both read,
  and the header already carries the id for anyone who needs it.

* **One structured line per request** — method, route *template*, status,
  duration. The template (`/api/drivers/{driver_id}`) rather than the concrete
  path, because 129 paths that are really one endpoint make a latency
  percentile meaningless. Concrete paths are logged for 4xx/5xx, where the
  specific value is usually the point.

  Levels are chosen so that filtering to `WARNING` is a useful default:
  `ERROR` for 5xx, `WARNING` for 4xx **and for any request slower than
  `F1_SLOW_REQUEST_MS`** (default 1000 ms — above the audit's slowest known-good
  endpoint, low enough to catch a regression rather than only an outage),
  `INFO` otherwise.

* **JSON output on demand.** `F1_LOG_FORMAT=json` emits one object per line,
  which every log aggregator parses without a custom rule, and which a message
  containing a newline cannot forge a second entry in. Text remains the default
  for local work.

That is deliberately all of it. **This project still builds no monitoring
infrastructure of its own** — no `/metrics` endpoint, no counters, no storage.
An in-process counter resets on every deploy and is per worker, so it would be
a number that looks authoritative and is not. Emitting a clean structured
stream and letting the platform aggregate the 5xx rate and the p95 is the same
judgement as before, now actually actionable.

### What the frontend does

`frontend/src/services/reporting.ts` is the single point every client-side
failure passes through. It closed a real coverage gap: `ErrorBoundary` catches
a component that throws *while rendering*, which is one of three ways this app
can fail. The other two reached nothing at all —

* an error thrown in an event handler or a timer, which React does not route
  to a boundary;
* a rejected promise nobody handled.

Both are captured now, via `window` `error` and `unhandledrejection` handlers
installed in `main.tsx` before the first render. Reports are normalised (a
`throw "string"` and a non-`Error` rejection reason both survive), carry the
route the reader was on, and are **de-duplicated** — a render loop throwing
every frame reports once, not four hundred times.

### The part that is still a decision, not a default

**By default, captured frontend errors go to the browser console and no
further.** They are captured, normalised and de-duplicated; they are not
transmitted. A console message in a visitor's browser tells nobody anything,
and this document would be lying if it implied otherwise.

Making them leave the browser needs a sink, which is a deployment choice, so
the code exposes a seam rather than a hardcoded vendor: call `setReporter`
once at startup and every captured error flows to it. Two supported options:

1. **Install an SDK.** `npm i @sentry/browser`, then in `main.tsx`:
   ```ts
   import * as Sentry from "@sentry/browser";
   Sentry.init({ dsn: import.meta.env.VITE_SENTRY_DSN });
   setReporter((entry) => Sentry.captureException(new Error(entry.message), { extra: entry }));
   ```
   No SDK is imported today on purpose: shipping ~30 KB to every visitor for a
   seam a deployment may never use is a cost with no current benefit.

2. **Post them to the API**, so client errors land in the same structured log
   stream as server errors. **This is not implemented, and should not be added
   without deciding one thing first:** the API is read-only and its CORS
   middleware allows `GET` only. A public `POST /api/client-errors` is a
   write endpoint on a read-only service and an unauthenticated log-flooding
   target, so it needs a size cap and a rate limit in the same change. That is
   a real architectural decision, not a wiring task, which is why it is written
   down here rather than quietly shipped.

**The API side has the same shape.** `F1_SENTRY_DSN` initialises Sentry *if*
`sentry-sdk` is installed; it is not a dependency of this project either. A DSN
set with no SDK present logs `MISCONFIGURED` at startup and reports nothing —
loudly, because a deployment that believes it has error reporting and does not
is worse than one that knows it has none. Startup always states which of the
three states it is in.

### Still worth doing before a public launch

1. **An uptime check on `/api/health`** — catches the whole class of "it's
   down", and this project does not provide it. Note the endpoint dispatches
   through the active backend rather than reading SQLite unconditionally, so a
   store outage surfaces here as a 503 instead of a cheerful 200.
2. **Pick a sink** for the error reports both sides now produce (above).
3. **Alerting thresholds** on the 5xx rate and p95 the logs now support. The
   audit measured `dataset/summary` at 400–500 ms and `records` at ~340 ms as
   the slowest endpoints, with everything else under 200 ms.

Instrumentation is not monitoring until something is watching. Items 1–3 are
what "watching" means here, and none of them is code in this repository.

---

## 7. Routine maintenance

| Task | When | Command |
|---|---|---|
| Re-run integrity audit | After any ingestion | `python -m backend.etl.audit` |
| Cross-validate against Jolpica | After ingestion, needs network | `python -m backend.etl.crossvalidate` |
| Prove the rebuild is deterministic | Runs inside the test suite | `python -m pytest backend/tests/test_reproducibility.py` |
| Verify migration checksums | After any schema change | `python supabase/verify_migrations.py` |
| Backend tests | Before every deploy | `python -m pytest backend/tests -q` |
| Frontend tests | Before every deploy | `cd frontend && npm test` |
| **Re-verify Supabase parity** | After any migration, ingestion or restore | `python -m pytest backend/tests/test_supabase.py backend/tests/test_store_parity.py backend/tests/test_backend_parity.py backend/tests/test_api_payload_parity.py -q` — then re-date the table in §4 |
| Dependency advisories | Monthly | `cd frontend && npm audit --omit=dev` |

CI (`.github/workflows/ci.yml`) runs the build, both test suites, the data
audit, the migration checksums and the production build on every push.

**CI proves the SQLite leg only, and that is on purpose.** It holds no
Supabase credentials, so every Supabase test skips there — deliberately, since
adding the secrets to a workflow with a `pull_request` trigger would attach
them to a fork's pull request. A green CI badge therefore says nothing about
Supabase parity, and reading it as if it did is the exact mistake the §4 table
exists to prevent.

`.github/workflows/supabase-parity.yml` closes that gap without reopening the
fork problem: it runs the four parity suites against the live project, is
triggered only by a push to `main` or a manual dispatch (**never**
`pull_request`), and is additionally guarded on the repository owner so a fork
cannot run it. It stays inert until `SUPABASE_URL` and `SUPABASE_ANON_KEY` are
added as repository secrets, and reports loudly rather than silently green if
they are missing.

### Standing advisory assessments

`npm audit` reports findings; it does not assess them. Assessments that were
deliberately not acted on are recorded here, so the next monthly run does not
re-open a settled question.

**The table is currently empty: `npm audit` reports 0 vulnerabilities, with
and without `--omit=dev`.** There is nothing being tolerated.

The two `react-router` advisories that used to sit here were closed at the
release-candidate gate by upgrading react-router 6 → 7, rather than by keeping
the exemption. The reasoning that had justified waiting — the vulnerable
`deserializeErrors()` path only runs during SSR hydration, and this is a
client-only SPA that calls `createRoot`, never `hydrateRoot` — still held. It
was simply cheaper to take the major than to keep explaining it: the app uses
only the stable core API (`BrowserRouter`, `Routes`, `Route`, `Link`,
`NavLink`, `Outlet`, `useNavigate`, `useLocation`, `useParams`,
`useSearchParams`, `MemoryRouter`), all unchanged in 7, and the upgrade landed
with the full suite green.

The dev toolchain (`vite` 5 → 8, `vitest` 2 → 4, `@vitejs/plugin-react` 4 → 6)
was upgraded in the same pass. Those advisories never shipped to a browser —
they affect the dev server and test runner — but leaving a *critical* line in
`npm audit` output trains the next reader to skim past it.

Re-check this section whenever `npm audit` output changes shape, and delete a
row the moment its reasoning stops holding. A stale exemption is worse than no
exemption, because it silences a real finding.
