"""Which data store serves a request, and what it is able to serve.

WHY THIS EXISTS
---------------
Before this module the project had two materialisations of the same CSV --
SQLite and Supabase -- and no way to choose between them. `supabase_repo.py`
was imported by nothing but its own tests, so the Postgres schema, its views
and its RLS were real work sitting entirely off the request path. That is the
"two conflicting versions of the same data" the project brief rules out: not
because the numbers disagree (they are reconciled), but because only one of
them was ever exercised.

THE HONEST PART
---------------
Selecting Supabase does not make every endpoint work. `supabase_repo` covers a
subset of the API surface, and the remaining endpoints have no Postgres
implementation yet. This module therefore carries an explicit capability set
rather than a boolean.

The rule it enforces: **an unsupported endpoint fails loudly.** It must never
quietly serve the SQLite answer while claiming to be on Supabase, because a
silent fallback would make the backend switch untestable -- every parity test
would pass by comparing SQLite against itself.

STATUS
------
The Supabase leg is *selectable but unexecuted*. A fresh clone has no `.env`,
so SUPABASE_URL / SUPABASE_ANON_KEY are unset, `supabase_repo.configured()` is
False, and asking for the Supabase backend raises at startup instead of
degrading. Nothing in this file has been run against the hosted project; the
parity suite in `backend/tests/test_backend_parity.py` is what would prove it,
and it skips without credentials.
"""

from __future__ import annotations

import os

from backend.app import supabase_repo

SQLITE = "sqlite"
SUPABASE = "supabase"
VALID = frozenset({SQLITE, SUPABASE})

# Endpoints `supabase_repo` genuinely implements today, each backed by a view
# that exists in migration 06. Anything absent from this set has no Postgres
# implementation -- listing it here to look complete would be the exact failure
# this module was written to prevent.
SUPABASE_CAPABILITIES = frozenset({
    "health",
    "driver_career_stats",
    "teammate_records",
    "records",
    "metric_definitions",
})


class BackendUnavailable(RuntimeError):
    """The selected backend cannot serve requests. Surfaces as a 503."""


class CapabilityMissing(RuntimeError):
    """The selected backend has no implementation for this endpoint.

    Deliberately not a fallback: see the module docstring.
    """


def selected() -> str:
    """The configured backend name. Defaults to SQLite.

    SQLite is the default because it is the only leg with no external
    dependency -- a fresh clone must build and serve without credentials.
    """
    name = os.getenv("F1_BACKEND", SQLITE).strip().lower()
    if name not in VALID:
        raise BackendUnavailable(
            f"F1_BACKEND={name!r} is not a backend. Valid: {', '.join(sorted(VALID))}"
        )
    return name


def check_ready(name: str | None = None) -> str:
    """Validate the selected backend at startup, raising rather than degrading.

    Called once when the app boots so a misconfiguration is a loud failure on
    launch, not an intermittent 503 discovered in production.
    """
    name = name or selected()
    if name == SUPABASE and not supabase_repo.configured():
        raise BackendUnavailable(
            "F1_BACKEND=supabase but SUPABASE_URL / SUPABASE_ANON_KEY are unset. "
            "Set both in .env, or leave F1_BACKEND unset to use SQLite."
        )
    return name


def supports(endpoint: str, name: str | None = None) -> bool:
    name = name or selected()
    return name == SQLITE or endpoint in SUPABASE_CAPABILITIES


def require(endpoint: str, name: str | None = None) -> str:
    """Assert the active backend implements `endpoint`, else raise.

    The raise is the point. Returning a SQLite result here would make the
    Supabase backend appear to work while never being exercised.
    """
    name = name or selected()
    if not supports(endpoint, name):
        raise CapabilityMissing(
            f"backend {name!r} has no implementation for {endpoint!r}. "
            f"Implemented: {', '.join(sorted(SUPABASE_CAPABILITIES))}"
        )
    return name


def describe() -> dict:
    """Backend state, for /api/health.

    Reports what is *actually* true, including the unexecuted status of the
    Supabase leg, so the running system does not overstate itself.
    """
    name = selected()
    return {
        "backend": name,
        "supabase_configured": supabase_repo.configured(),
        "unsupported_endpoints_fail": True,
        "capabilities": (
            "all" if name == SQLITE else sorted(SUPABASE_CAPABILITIES)
        ),
    }
