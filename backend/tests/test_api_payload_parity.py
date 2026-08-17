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
    "/api/compare/drivers?left=1&right=2",
    "/api/cars",
    "/api/dataset/summary",
]


def _client(monkeypatch, backend: str) -> TestClient:
    """An app instance bound to one backend.

    The backend is read at import time in main.py, deliberately -- a
    misconfiguration should fail on launch rather than as an intermittent 503.
    That means switching it requires reimporting the module rather than just
    setting the variable.
    """
    monkeypatch.setenv("F1_BACKEND", backend)
    import backend.app.main as main

    importlib.reload(main)
    return TestClient(main.app)


@pytest.fixture
def clients(monkeypatch):
    sqlite_client = _client(monkeypatch, "sqlite")
    supabase_client = _client(monkeypatch, "supabase")
    yield sqlite_client, supabase_client
    # Leave the module bound to the default, or every later test in the
    # session inherits a Supabase-backed app.
    monkeypatch.delenv("F1_BACKEND", raising=False)
    import backend.app.main as main

    importlib.reload(main)


def _normalise(value):
    """Strip differences that are representation, not disagreement.

    Postgres returns numerics with more decimal places than SQLite's floats;
    rounding to six places compares the values rather than their spelling.
    Anything that survives this is a real difference.
    """
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


@pytest.mark.parametrize("path", DISPATCHED_PATHS)
def test_dispatched_endpoints_return_identical_payloads(clients, path):
    sqlite_client, supabase_client = clients

    left = sqlite_client.get(path)
    right = supabase_client.get(path)

    assert left.status_code == right.status_code == 200, (
        f"{path}: sqlite {left.status_code}, supabase {right.status_code}"
    )
    assert _normalise(left.json()) == _normalise(right.json()), (
        f"{path} differs between backends"
    )


def test_supabase_backend_reports_itself_in_health(clients):
    """/api/health must say which store answered.

    A reader should never have to infer the backend from the numbers -- which
    is exactly what they would have to do if the two agreed and neither said
    so.
    """
    _, supabase_client = clients
    body = supabase_client.get("/api/health").json()
    assert body["backend"] == "supabase"
    assert body["supabase_configured"] is True


def test_undispatched_endpoint_fails_loudly_on_supabase(clients):
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
