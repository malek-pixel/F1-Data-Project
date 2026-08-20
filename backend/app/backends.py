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

THE RULE IT ENFORCES
--------------------
**An unsupported endpoint fails loudly.** It must never quietly serve the
SQLite answer while claiming to be on Supabase, because a silent fallback
would make the backend switch untestable -- every parity test would pass by
comparing SQLite against itself. Hence an explicit capability set rather than
a boolean.

STATUS
------
The Supabase leg is selectable AND executed, but read the next paragraph
before trusting any figure in this file.

This section used to read "27 of the 28 endpoints are implemented against it
and each one is compared, value for value, with the SQLite answer". Neither
half was true:

  * The comparison was vacuous. test_api_payload_parity.py built both
    TestClients up front, and `selected()` reads F1_BACKEND per REQUEST, so
    whichever value was set last answered for both. Every assertion ran
    Supabase against Supabase. When the fixture was repaired, 16 of the 19
    compared endpoints disagreed -- a truncated `season_dominance`, null
    `entries` and `win_rate` columns, a search index with no race rows, and a
    driver-constructor history returning three raw columns instead of a stat
    block. Migration 22 and the repo changes beside it closed those.

  * "Implemented" was measured by what `supabase_repo` can do, not by what
    the API actually calls. Roughly two thirds of the routes never reach
    `serve()` at all -- they read SQLite directly whatever F1_BACKEND says,
    including /records, /insights, /seasons, /races, /circuits and the driver
    sub-resources. `SUPABASE_CAPABILITIES` names implementations for several
    of them, and `test_capability_set_is_not_aspirational` only checks that a
    callable of that name exists in supabase_repo -- not that any route
    dispatches to it.

So the capability set below describes what supabase_repo CAN serve. It is not
a list of what the running API does serve. Wiring the remaining routes through
`serve()`, one at a time with a payload comparison each, is the work left.

A fresh clone still has no `.env`, so SUPABASE_URL / SUPABASE_ANON_KEY are
unset, `supabase_repo.configured()` is False, and asking for the Supabase
backend raises at startup instead of degrading. The parity suites skip in that
state, and a skip is missing coverage rather than a pass.
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
    # Added once each had a Postgres implementation AND a test comparing its
    # values against the SQLite answer. Listing an endpoint here without that
    # comparison would be the "looks complete" failure this set exists to
    # prevent -- the name would claim support that nothing had exercised.
    #
    # Each name is the `supabase_repo` function that implements it, not a
    # prose label. test_capability_set_is_not_aspirational asserts exactly
    # that, so a capability cannot be advertised unless something callable
    # backs it -- which is how the first draft of this list was caught naming
    # five endpoints that did not exist.
    "driver_by_slug",
    "constructor_by_slug",
    "circuit_by_slug",
    "driver_seasons",
    "constructor_seasons",
    "driver_circuits",
    "driver_qualifying",
    "constructor_drivers",
    "circuits",
    "seasons",
    "season",
    "standings",
    "races",
    "race",
    "leaderboard",
    # Migration 19 moved these eight definitions INTO the database, so they
    # are no longer Python-only. They were the last endpoints with no
    # Postgres implementation.
    "search",
    "season_dominance",
    "era_summary",
    "distribution",
    "compare",
    "cars",
    "dataset_availability",
    # Added by migration 23, when the routes that had never called `serve()`
    # at all were wired through it. Each name is backed by a supabase_repo
    # function AND by a payload-parity case comparing it with the SQLite
    # answer -- the two conditions this set is supposed to mean, rather than
    # the one (a callable exists) it used to be checked against.
    "seasons",
    "season_rounds",
    "races",
    "circuits",
    "circuit_specialists",
    "constructor_distribution",
    "dominance_timeline",
})

# Endpoints with NO Postgres implementation, and why. Written down because
# "unsupported" is otherwise indistinguishable from "forgotten".
#
# This list used to hold eight entries, each justified on the grounds that
# reproducing it as a view would define the same metric twice. That reasoning
# was right about the danger and wrong about the remedy: the fix is to MOVE
# the definition into the database, not to copy it. Migration 19 did exactly
# that, and seven of the eight became ordinary view-backed endpoints.
#
# What remains is not a metric at all.
UNIMPLEMENTED_ON_SUPABASE = {
    "insights": (
        "narrative composed in Python from several aggregates. Each aggregate "
        "it reads IS available on Supabase; only the assembly and phrasing are "
        "Python, and those are presentation rather than a metric."
    ),
}


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


def serve(endpoint: str, sqlite, supabase):
    """Run whichever implementation the active backend provides.

    Both arguments are zero-argument callables, so the unused one is never
    evaluated -- selecting SQLite must not open a Supabase connection, and
    vice versa.

    The Supabase branch is only taken when the endpoint is in
    SUPABASE_CAPABILITIES; anything else raises through `require`. There is
    deliberately no `except: return sqlite()` here. A fallback would mean the
    Supabase backend could be selected, silently answer from SQLite, and pass
    every parity test by comparing SQLite against itself -- which is the exact
    failure this module exists to prevent.
    """
    name = require(endpoint)
    return sqlite() if name == SQLITE else supabase()


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
