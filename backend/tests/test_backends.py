"""The backend switch, and the parity harness that would prove it.

Two halves:

  * **Switch semantics** -- run always. These prove the selection logic, and in
    particular that an unsupported endpoint RAISES rather than silently
    returning the SQLite answer. That single property is what makes the
    Supabase leg testable at all: with a fallback, every parity test would
    pass by comparing SQLite against itself.

  * **Parity** -- skips without credentials. This is the suite that would show
    both stores return the same numbers. It has never run: a fresh clone has
    no `.env`, so it skips, and skipping proves nothing. Said plainly here so
    a green suite is not mistaken for a verified Supabase backend.
"""

from __future__ import annotations

import pytest

from backend.app import backends, supabase_repo


# --------------------------------------------------------------- switch


def test_defaults_to_sqlite(monkeypatch):
    """A fresh clone must serve without any credential."""
    monkeypatch.delenv("F1_BACKEND", raising=False)
    assert backends.selected() == backends.SQLITE


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("F1_BACKEND", "mysql")
    with pytest.raises(backends.BackendUnavailable):
        backends.selected()


def test_supabase_without_credentials_refuses_to_start(monkeypatch):
    """The important negative case: refuse, never degrade to SQLite."""
    monkeypatch.setenv("F1_BACKEND", "supabase")
    monkeypatch.setattr(supabase_repo, "configured", lambda: False)
    with pytest.raises(backends.BackendUnavailable):
        backends.check_ready()


def test_sqlite_supports_every_endpoint(monkeypatch):
    monkeypatch.setenv("F1_BACKEND", "sqlite")
    for endpoint in ("health", "records", "leaderboard", "anything_at_all"):
        assert backends.supports(endpoint)


def test_supabase_reports_only_what_it_implements(monkeypatch):
    monkeypatch.setenv("F1_BACKEND", "supabase")
    assert backends.supports("driver_career_stats")
    # `insights` is the one endpoint with no Supabase implementation, and
    # deliberately so: it is a narrative composed in Python from aggregates
    # that ARE all available on Supabase. Only the assembly and phrasing are
    # Python, and those are presentation rather than a metric.
    #
    # `search` used to be the example here. It is supported now -- migration
    # 19 moved its definition into the database.
    assert not backends.supports("insights")


def test_unsupported_endpoint_raises_rather_than_falling_back(monkeypatch):
    """No silent fallback. This is the whole design of the module."""
    monkeypatch.setenv("F1_BACKEND", "supabase")
    with pytest.raises(backends.CapabilityMissing):
        backends.require("insights")


def test_capability_set_is_not_aspirational():
    """Every advertised capability must be a real callable on the repo."""
    for name in backends.SUPABASE_CAPABILITIES:
        assert callable(getattr(supabase_repo, name, None)), (
            f"{name!r} is advertised as a Supabase capability but "
            f"supabase_repo has no such function"
        )


def test_health_describes_the_active_backend(monkeypatch):
    monkeypatch.delenv("F1_BACKEND", raising=False)
    described = backends.describe()
    assert described["backend"] == backends.SQLITE
    assert described["capabilities"] == "all"
    assert described["unsupported_endpoints_fail"] is True


# --------------------------------------------------------------- parity

parity = pytest.mark.skipif(
    not supabase_repo.configured(),
    reason="SUPABASE_URL / SUPABASE_ANON_KEY unset -- parity unproven, not proven-good",
)


@parity
def test_health_agrees_across_backends():
    """Coverage and entity counts must match between the two stores."""
    from backend.app.db import connect

    remote = supabase_repo.health()
    conn = connect()
    try:
        row = conn.execute(
            "SELECT MIN(season) AS lo, MAX(season) AS hi, COUNT(*) AS races FROM races"
        ).fetchone()
        local_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("results", "drivers", "constructors", "circuits")
        }
    finally:
        conn.close()

    assert remote["season_from"] == row["lo"]
    assert remote["season_to"] == row["hi"]
    assert remote["races"] == row["races"]
    for table, count in local_counts.items():
        assert remote[table] == count, f"{table}: supabase {remote[table]} vs sqlite {count}"


@parity
def test_driver_ids_are_not_interchangeable_across_backends():
    """Documents a real defect rather than pretending the ids line up.

    Both stores assign `drivers.id` positionally from a name sort, but they
    sort differently: SQLite compares raw bytes, so "Andrea" < "André"
    ('a' = 0x61 < 'é' = 0xC3A9), while Postgres uses a locale-aware
    collation that reads "André" < "Andrea". Every accented name shifts the
    numbering from that point on.

    Measured 2026-08-13: id 7 is André Lotterer on Supabase and Andrea Kimi
    Antonelli on SQLite; 8 is the reverse. Circuits are unaffected (they carry
    a slug); drivers and constructors are not.

    The consequence is that `/drivers/7` means a different person depending on
    the backend, so no cross-store comparison may join on the surrogate id.
    """
    remote_rows, _ = supabase_repo.query("drivers", select="id,display_name")
    remote = {row["display_name"]: row["id"] for row in remote_rows}

    from backend.app.db import connect

    conn = connect()
    try:
        local = {name: ident for ident, name in conn.execute("SELECT id, name FROM drivers")}
    finally:
        conn.close()

    assert set(remote) == set(local), "the two stores disagree on which drivers exist"
    # The ids are NOT expected to match. Asserting they do would be wrong; this
    # pins the known divergence so a future id-stability fix is noticed here.
    assert any(remote[name] != local[name] for name in local), (
        "driver ids now agree across backends -- if that was fixed deliberately, "
        "update this test and docs/BACKEND_CHECKLIST.md"
    )


@parity
def test_driver_career_stats_agree_across_backends():
    """Same driver, same numbers, from two independent implementations.

    Joined on NAME, never on id -- see the test above for why the surrogate
    ids are not comparable between the two stores.
    """
    from backend.app import analytics
    from backend.app.db import connect

    remote_rows, _ = supabase_repo.query("drivers", select="id,display_name")
    remote_id = {row["display_name"]: row["id"] for row in remote_rows}

    conn = connect()
    try:
        drivers = conn.execute(
            "SELECT d.id, d.name, COUNT(*) AS entries FROM drivers d"
            " JOIN results r ON r.driver_id = d.id"
            " GROUP BY d.id ORDER BY entries DESC, d.name LIMIT 5"
        ).fetchall()

        for driver in drivers:
            name = driver["name"]
            assert name in remote_id, f"{name} missing from Supabase"
            remote = supabase_repo.driver_career_stats(remote_id[name])
            assert remote is not None, f"{name} has no Supabase career stats"
            local = analytics.entity_stats(conn, "driver", driver["id"])
            for key in ("entries", "wins", "podiums", "top10"):
                assert remote[key] == local[key], (
                    f"{name} {key}: supabase {remote[key]} vs sqlite {local[key]}"
                )
    finally:
        conn.close()
