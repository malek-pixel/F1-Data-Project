# QA matrix — frontend ↔ Supabase integration phase

Every row was exercised. Where something was not tested, the row says so
rather than being marked green.

**How things were tested.** The whole app was run against the hosted Supabase
project (`F1_BACKEND=supabase`) and driven in a browser; every endpoint was
compared response-for-response against the SQLite answer by
`test_api_payload_parity.py` (77 paths); 351 backend and 49 frontend tests
pass.

| Area | Status | Issues found | Fixed |
|---|---|---|---|
| Backend dispatch | ✅ tested | 19 of 30 routes never called `serve()` — they read SQLite whatever `F1_BACKEND` said | ✅ 28/30 dispatch; the 2 exceptions are documented and one now returns 501 instead of a silent answer |
| Payload parity | ✅ tested | The parity fixture compared Supabase against itself; 16 of 19 endpoints in fact disagreed | ✅ Fixture rebound per request + guard test; 77 paths compared, all agree |
| Home | ✅ tested | Absence list claimed lap times / fastest lap / tyre compounds were missing beside a panel showing 552,138 lap rows | ✅ Availability probed per field |
| Drivers | ✅ tested | Team history returned 3 raw columns; nationality, car number, qualifying and DNF rate shown as "to be added" while the API returned all four | ✅ View added; all four rendered, degrading per driver |
| Constructors | ✅ tested | `win_rate` and `best_classified_position` null for all 26 seasons; career block missing top5/rates/avg_grid | ✅ Columns added to both views |
| Circuits | ✅ tested | `races` absent from the detail payload (rendered as an em dash in 3 places); index ordered differently per backend | ✅ Count added; `collate "C"` sort key |
| Races | ✅ tested | Whole route SQLite-only; Postgres had **no fastest-lap columns at all**; Status column hardcoded "unavailable" | ✅ Route wired; migration 24 + backfill of 8,725 rows; status rendered |
| Seasons | ✅ tested | "Champions require a points column; the source has none" — while Home displayed the champion | ✅ Points leader rendered, labelled as leader not adjudicated champion |
| Search | ✅ tested | Index held no race or season rows; "ham" gave 3 hits vs 11 and ranked Caterham above Hamilton; SQLite ranked country-only matches first ("spa" → Barcelona) | ✅ Index extended; per-kind limits; both ranking bugs fixed |
| Filters | ✅ tested | — (search/season filters remain SQLite-only by design, documented at the call site) | n/a |
| Sorting | ✅ tested | No tiebreaks on Supabase vs three on SQLite; `sort=name` differed by collation | ✅ Identical tiebreak chains ending in `slug`; `collate "C"` sort keys |
| Pagination | ✅ tested | Past-the-end offset returned 416 → surfaced as "Data store unavailable" | ✅ 416 treated as an empty page; 129 rows walked, 0 dupes, 0 overlap across 7 sorts on both backends |
| Charts | ✅ tested | Season dominance dropped the entire constructor half on Supabase | ✅ View extended; charts render |
| Tables | ✅ tested | Career-log DNF column hardcoded `n/a` | ✅ Real per-season counts |
| Images / logos | ✅ tested | None — 26 images on the drivers page, all with `alt`; missing assets fall back to a named frame | n/a |
| Supabase integration | ✅ tested | See dispatch and parity rows | ✅ |
| Security | ✅ tested | None. RLS on all 20 tables; anon has SELECT only (9 write attempts → 401); staging blocked; publishable key never reaches the browser (0 references in the built bundle); no service-role key in `.env` | n/a |
| Error states | ✅ tested | Supabase outage escaped as a bare 500 with no body; `/api/insights` answered 200 from SQLite under Supabase | ✅ 503 + `detail` handler; 501 for unimplemented; 11 invalid inputs all 4xx with no internals leaked |
| Performance | ✅ tested | `/api/records` 13 requests / 3.6s; race weekend 10 requests | ✅ Records 2,964ms → **5ms** warm; circuits/seasons/eras/dominance ~5ms warm |
| Caching | ✅ tested | None pre-existing | ✅ 300s TTL on identity + whole-dataset aggregates only; nothing season-scoped |
| Mobile (375) | ✅ tested | None — no horizontal overflow on 11 pages | n/a |
| Tablet (768) | ✅ tested | None | n/a |
| Desktop (1280) | ✅ tested | None | n/a |
| Accessibility | ⚠️ partial | None found: across 10 pages, 0 images without `alt`, 0 unnamed buttons/links, 0 unlabelled inputs, one `h1` each, no heading skips, `lang="en"`, skip link present, no positive tabindex | Not tested: screen-reader walkthrough, colour-contrast ratios, full keyboard traversal |
| Historical eras | ✅ tested | None — 2000/2005/2010/2014/2021/2025 all render; a 2000 race correctly shows fastest-lap-award unavailable while showing a real quickest lap | n/a |
| Test reliability | ✅ tested | A run failed 64 tests on SSL/connection errors — transient network drop to Supabase | ✅ Bounded retry (3 attempts, backoff) on connection failures and 5xx; 4xx never retried |

## Not covered by this phase

- Screen-reader and colour-contrast auditing.
- Load or concurrency testing. Latency was measured single-threaded from one
  machine; ~270ms per PostgREST round trip is the dominant term.
- The three dataset-wide records the UI lists as "not built yet" (most
  qualifying P1, most WCC titles, fewest DNFs per race). The data exists; the
  records are not implemented, and the panel says exactly that.
- `constructor_id` filtering on the driver listing has no Supabase
  implementation and stays on SQLite.
