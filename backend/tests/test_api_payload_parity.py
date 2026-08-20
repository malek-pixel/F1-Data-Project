"""The same request, on both backends, must return the same JSON.

This is the last of the three parity suites and the only one that exercises
the actual application:

  * test_store_parity.py       -- the two DATABASES hold the same rows
  * test_backend_parity.py     -- the two IMPLEMENTATIONS compute the same numbers
  * this file                  -- the two BACKENDS serve the same HTTP response

The first two can both pass while the API is still broken under
F1_BACKEND=supabase, because the views name things as the database does
(`display_name`, `driver_slug`) and the contract names them as analytics.py
does (`name`, `slug`). A backend switch that changes the shape of every
payload is not a backend switch; it is a second, incompatible API sharing a
URL. Only a comparison of the responses themselves catches that.

Skips without credentials, and a skip is missing coverage rather than a pass.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from backend.app import env as _env  # noqa: F401  (loads .env before the check)
from backend.app import supabase_repo
from backend.app.db import DB_PATH

pytestmark = [
    pytest.mark.skipif(
        not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
    ),
    pytest.mark.skipif(
        not supabase_repo.configured(),
        reason="SUPABASE_URL / SUPABASE_ANON_KEY unset -- API payload parity unverified",
    ),
]

# Endpoints wired through backends.serve. Each must answer identically under
# both backends. Anything absent from this list is either SQLite-only by
# design (see backends.UNIMPLEMENTED_ON_SUPABASE) or not yet dispatched.
DISPATCHED_PATHS = [
    "/api/drivers?limit=5",
    "/api/drivers?limit=5&sort=podiums",
    "/api/drivers/hamilton",
    "/api/drivers/max_verstappen",
    "/api/drivers/hamilton/seasons",
    "/api/constructors/ferrari",
    "/api/seasons/2025/standings",
    "/api/seasons/2021/standings",
    "/api/seasons/2000/standings",
    # The seven whose definitions moved into the database in migration 19.
    # Each was previously SQLite-only.
    "/api/search?q=ham",
    "/api/search?q=ferrari",
    "/api/drivers/hamilton/distribution",
    "/api/drivers/aitken/distribution",
    "/api/seasons/2023/dominance",
    "/api/seasons/2021/dominance",
    "/api/analytics/eras",
    "/api/compare/drivers?left=hamilton&right=alonso",
    "/api/cars",
    "/api/dataset/summary",
    # Added after the fixture was repaired. The list above was the whole of
    # the coverage while every comparison in it was vacuous, so the endpoints
    # below had never been compared even nominally. Spread across eras
    # deliberately: 2000 predates the enrichment columns that 2021+ carries,
    # and sprints exist only from 2021.
    "/api/drivers/michael_schumacher",
    "/api/drivers/hamilton/teammates",
    "/api/drivers/hamilton/circuits",
    "/api/drivers/hamilton/qualifying",
    "/api/constructors/ferrari/drivers",
    "/api/constructors/mclaren",
    "/api/constructors/brawn",
    "/api/circuits",
    "/api/circuits/monza",
    "/api/seasons",
    "/api/seasons/2000",
    "/api/seasons/2014",
    "/api/seasons/2000/rounds",
    "/api/seasons/2025/rounds",
    "/api/seasons/2000/dominance",
    "/api/races?season=2000",
    "/api/races?season=2021",
    "/api/records",
    "/api/drivers?limit=200",
    "/api/drivers?sort=win_rate&limit=20",
    "/api/drivers?sort=name&limit=20",
    "/api/drivers?search=schumacher",
    "/api/drivers?min_entries=100&limit=50",
    "/api/constructors?limit=200",
    "/api/constructors?sort=podiums&limit=20",
    "/api/search?q=alonso",
    "/api/search?q=2004 monza",
    "/api/search?q=spa",
    "/api/search?q=2004",
    "/api/search?q=zzzznothing",
    "/api/analytics/metrics",
    # Added when the routes that had never reached serve() at all were wired
    # through it (migration 23). Every one of these read SQLite whatever
    # F1_BACKEND said, so this is their first comparison of any kind.
    "/api/seasons",
    "/api/seasons/2000/rounds",
    "/api/seasons/2021/rounds",
    "/api/races?season=2005",
    "/api/races?limit=30",
    "/api/circuits",
    "/api/circuits/monza",
    "/api/circuits/spa",
    "/api/circuits/monza/specialists",
    "/api/circuits/monza/specialists?min_appearances=8",
    "/api/constructors?limit=100",
    "/api/constructors/ferrari/drivers",
    "/api/constructors/ferrari/distribution",
    "/api/drivers/hamilton/circuits?min_appearances=8",
    "/api/analytics/dominance",
    "/api/records",
    "/api/seasons/2010/rounds",
    # Pagination, including past the last row. PostgREST answers an
    # out-of-range offset with 416, which this used to surface as "Data
    # store unavailable" while SQLite returned an empty page.
    "/api/drivers?limit=25&offset=100",
    "/api/drivers?limit=25&offset=125",
    "/api/drivers?limit=25&offset=500",
    "/api/constructors?limit=25&offset=200",
    "/api/drivers?limit=10&offset=10&sort=win_rate",
    "/api/drivers?limit=10&offset=10&sort=name",
    # The race weekend: classification, qualifying, sprint, pit stops,
    # practice and both fastest laps. Spread across eras because each block
    # has its own coverage window.
    "/api/races/500",
    "/api/races/1",
    "/api/races/300",
    "/api/races/460",
]


def _bind(monkeypatch, store: str) -> TestClient:
    """An app instance bound to `store`, rebound immediately before each use.

    `backends.selected()` reads F1_BACKEND on every *request*, not at import,
    so holding two clients at once does not give you two backends: whichever
    value was set last answers for both. The previous version of this file
    built both clients up front and compared them, which meant every
    assertion below ran Supabase against Supabase and passed vacuously --
    exactly the "comparing a store against itself" failure that
    backends.py's docstring warns about. It hid a truncated
    `season_dominance` payload and a null `entries` column for as long as it
    existed.

    So: set the variable, reload, build the client, and issue the request
    before anything else can move it.
    """
    monkeypatch.setenv("F1_BACKEND", store)
    import backend.app.main as main

    importlib.reload(main)
    return TestClient(main.app)


@pytest.fixture
def fetch(monkeypatch):
    """`fetch(store, path)` -> Response, with the backend bound per call."""

    def _fetch(store: str, path: str):
        return _bind(monkeypatch, store).get(path)

    yield _fetch
    # Leave the module bound to the default, or every later test in the
    # session inherits whichever backend ran last.
    monkeypatch.delenv("F1_BACKEND", raising=False)
    import backend.app.main as main

    importlib.reload(main)


# Surrogate keys. `drivers.id` is an autoincrement in SQLite and an identity
# column in Postgres, filled in a different order -- Hamilton is 48 on one and
# 65 on the other. That is not a disagreement about Hamilton; it is two stores
# numbering their rows independently, and no amount of view work makes them
# converge.
#
# They are dropped from the comparison rather than silently tolerated, and
# `slug` -- the key that DOES mean the same thing on both stores -- is left in
# and still compared strictly. test_slugs_are_compared_not_dropped below
# guarantees this exclusion cannot quietly widen to cover the portable key too.
STORE_LOCAL_KEYS = frozenset({
    "id", "constructor_id", "driver_id", "circuit_id", "race_id",
    # Winner and teammate references are the same surrogate keys reached
    # through a join, and diverge for the same reason.
    "winner_driver_id", "winner_constructor_id", "teammate_id", "season_id",
})


def _normalise(value):
    """Strip differences that are representation, not disagreement.

    Postgres returns numerics with more decimal places than SQLite's floats;
    rounding to six places compares the values rather than their spelling.
    Store-local surrogate ids are dropped, for the reason above. Anything that
    survives this is a real difference.
    """
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items() if k not in STORE_LOCAL_KEYS}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def test_slugs_are_compared_not_dropped():
    """The portable key must never join the store-local exclusion list.

    Dropping `slug` would let the two backends disagree about WHICH driver a
    row describes while every number still matched.
    """
    for key in ("slug", "driver_slug", "constructor_slug", "name", "display_name"):
        assert key not in STORE_LOCAL_KEYS
    assert _normalise({"id": 1, "slug": "hamilton"}) == {"slug": "hamilton"}


def test_each_client_actually_reports_its_own_backend(fetch):
    """Guard for the bug this file's fixture used to have.

    If this fails, every payload comparison below is comparing one store
    against itself and proves nothing.
    """
    assert fetch("sqlite", "/api/health").json()["backend"] == "sqlite"
    assert fetch("supabase", "/api/health").json()["backend"] == "supabase"


@pytest.mark.parametrize("path", DISPATCHED_PATHS)
def test_dispatched_endpoints_return_identical_payloads(fetch, path):
    left = fetch("sqlite", path)
    right = fetch("supabase", path)

    assert left.status_code == right.status_code == 200, (
        f"{path}: sqlite {left.status_code}, supabase {right.status_code}"
    )
    assert _normalise(left.json()) == _normalise(right.json()), (
        f"{path} differs between backends"
    )


def test_supabase_backend_reports_itself_in_health(fetch):
    """/api/health must say which store answered.

    A reader should never have to infer the backend from the numbers -- which
    is exactly what they would have to do if the two agreed and neither said
    so.
    """
    body = fetch("supabase", "/api/health").json()
    assert body["backend"] == "supabase"
    assert body["supabase_configured"] is True


def test_undispatched_endpoint_fails_loudly_on_supabase():
    """An endpoint with no Postgres implementation must not quietly work.

    `/api/insights` is the last SQLite-only endpoint, and by design: it
    composes a narrative in Python from aggregates that are themselves all
    available on Supabase. Under Supabase it has to raise rather than return
    the SQLite answer -- a silent fallback would let the whole parity suite
    pass by comparing SQLite against itself.
    """
    from backend.app import backends

    assert "insights" in backends.UNIMPLEMENTED_ON_SUPABASE
    with pytest.raises(backends.CapabilityMissing):
        backends.require("insights", backends.SUPABASE)


def test_supabase_outage_is_a_503_with_a_detail_body(monkeypatch):
    """A dead data store must not surface as a bare 500.

    Only sqlite3.Error had a handler, so a Supabase outage escaped as
    "Internal Server Error" with no JSON body -- against the documented
    contract (503, retryable, `detail`) and against the client, which reads
    `detail` to tell a reader what to do.

    Nothing about the credentials or the URL may appear in the response: they
    are in the exception text, and the exception text belongs in the log.
    """
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:1/dead")
    import backend.app.supabase_repo as repo

    importlib.reload(repo)
    try:
        client = _bind(monkeypatch, "supabase")
        response = client.get("/api/drivers/hamilton")
        assert response.status_code == 503
        assert response.json()["detail"] == "Data store unavailable. Retry shortly."
        body = response.text
        for secret in ("apikey", "127.0.0.1", "Traceback", "urllib"):
            assert secret not in body, f"{secret!r} leaked into the error response"
    finally:
        monkeypatch.undo()
        importlib.reload(repo)


def test_insights_fails_loudly_on_supabase_rather_than_answering_from_sqlite(monkeypatch):
    """The one unimplemented endpoint must refuse, not quietly serve SQLite.

    /api/insights never called serve() -- there is no Supabase branch for it
    to take -- so it ran the SQLite query whatever F1_BACKEND said and
    returned 200. That is the silent fallback backends.py forbids, on the
    single endpoint documented as unsupported.

    501, not 503: retrying will not help. Nothing is broken.
    """
    assert _bind(monkeypatch, "sqlite").get("/api/insights").status_code == 200

    response = _bind(monkeypatch, "supabase").get("/api/insights")
    assert response.status_code == 501
    assert "not available" in response.json()["detail"]
