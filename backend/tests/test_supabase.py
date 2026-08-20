"""Supabase schema, data-integrity, analytics and security tests.

Skipped when SUPABASE_URL / SUPABASE_ANON_KEY are absent, so the suite still
runs offline. When configured, these hit the real project through the same
public key the browser would use -- which is what makes the security
assertions meaningful rather than theoretical.
"""
from __future__ import annotations

import pytest

from backend.app import supabase_repo as repo

pytestmark = pytest.mark.skipif(
    not repo.configured(),
    reason="Supabase not configured (set SUPABASE_URL and SUPABASE_ANON_KEY)",
)

# Ground truth from results.csv, independently established.
EXPECTED = {"results": 10550, "races": 503, "seasons": 26,
            "drivers": 129, "constructors": 38, "circuits": 39}


# --------------------------------------------------------------------------
# Data reconciliation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("resource,expected", sorted(EXPECTED.items()))
def test_row_counts_reconcile_with_the_source(resource, expected):
    _, total = repo.query(resource, select="id" if resource != "seasons" else "id",
                          limit=1, exact_count=True)
    assert total == expected


def test_health_reports_real_coverage():
    info = repo.health()
    assert info["season_from"] == 2000
    assert info["season_to"] == 2025
    assert info["results"] == EXPECTED["results"]
    # This is a static historical dataset and must never claim otherwise.
    assert info["live_data"] is False


# --------------------------------------------------------------------------
# Analytics -- values verified against the independent Python implementation
# --------------------------------------------------------------------------

def test_driver_career_stats_match_known_values():
    rows, _ = repo.query("v_driver_career_stats",
                         filters={"display_name": "eq.Lewis Hamilton"})
    stats = rows[0]
    assert stats["entries"] == 380
    assert stats["wins"] == 105
    assert stats["podiums"] == 202
    assert float(stats["avg_classified_position"]) == pytest.approx(5.239)
    assert float(stats["median_classified_position"]) == 3


def test_rates_are_null_never_zero_by_default():
    """A driver with entries but no wins has win_rate 0.0; the NULL case is
    reserved for 'no data'. Confusing the two invents a result."""
    rows, _ = repo.query("v_driver_career_stats",
                         filters={"display_name": "eq.Adrian Sutil"})
    assert float(rows[0]["win_rate"]) == 0.0
    assert rows[0]["entries"] > 0


def test_small_samples_are_flagged_not_hidden():
    rows, _ = repo.query("v_driver_career_stats",
                         filters={"rates_reliable": "eq.false"}, select="entries")
    assert all(row["entries"] < 10 for row in rows)


def test_teammate_records_reconcile():
    spells = repo.teammate_records(
        repo.query("drivers", select="id", filters={"display_name": "eq.Lewis Hamilton"})[0][0]["id"]
    )
    bottas = next(s for s in spells if s["teammate_name"] == "Valtteri Bottas")
    assert bottas["shared_races"] == 100
    assert bottas["ahead"] == 75
    assert bottas["behind"] == 25


def test_teammate_totals_always_reconcile():
    rows, _ = repo.query("v_teammate_comparisons",
                         select="shared_races,ahead,behind", limit=500)
    for row in rows:
        assert row["ahead"] + row["behind"] == row["shared_races"]


def test_records_carry_methodology():
    for record in repo.records():
        assert record["methodology"]
        assert record["entity"]


def test_every_metric_definition_states_limitations():
    """A metric published without limitations reads as more authoritative than
    it is, so the column is NOT NULL and this asserts it stays meaningful."""
    definitions = repo.metric_definitions()
    assert len(definitions) >= 10
    for definition in definitions:
        assert definition["limitations"].strip()
        assert definition["formula"].strip()


def test_cars_table_is_empty_not_fabricated():
    """The Car Library needs the entity; the source has no car data. An empty
    table is honest, invented chassis specifications are not."""
    _, total = repo.query("cars", select="id", limit=1, exact_count=True)
    assert total == 0


def test_enrichment_columns_exist_and_are_populated():
    """The design rule, restated for the columns that now have a source.

    This test used to assert that `points`, `status`, `grid` and `laps` did
    NOT exist. That was the correct guarantee while no source supplied them:
    an all-NULL column invites zero-substitution and breaks every aggregate.

    A source now supplies them (Jolpica-F1, cross-validated across all 10,550
    rows), so the rule is not "these columns must be absent" -- it is "a column
    that exists must be populated, not a placeholder". That is what is checked
    here instead.
    """
    rows, _ = repo.query("results", select="*", limit=1)
    present = set(rows[0])
    for column in ("points", "grid", "laps", "status", "classification"):
        assert column in present, f"results lost its {column} column"

    # The fastest-lap columns joined this table in migration 24. They were on
    # the forbidden list above until then, correctly: Postgres had no source
    # for them. It does now -- the enrichment SQLite already carried was
    # loaded by backend/etl/backfill_fastest_lap.py -- so the rule that
    # applies is the same one as for points and grid: present means
    # populated, not a placeholder.
    for column in ("fastest_lap_rank", "fastest_lap_number", "fastest_lap_time"):
        assert column in present, f"results lost its {column} column"

    _, enriched = repo.query(
        "results", select="id", filters={"fastest_lap_rank": "not.is.null"},
        limit=1, exact_count=True,
    )
    assert enriched, "fastest_lap_rank exists but no row carries a value"

    # Still forbidden: no source provides these, so they must not appear.
    # `tyre_compound` belongs to practice_laps, which has a source; on a RACE
    # result it would have none.
    speculative = {"pit_stops", "tyre_compound", "race_time", "gap_to_winner"}
    assert not (speculative & present), "results gained a column with no source"

    # A column that exists must carry values. One NULL row would be enough to
    # reintroduce exactly the ambiguity the original rule was protecting.
    _, unpopulated = repo.query(
        "results", select="id", filters={"classification": "is.null"},
        limit=1, exact_count=True,
    )
    assert unpopulated == 0, f"{unpopulated} result rows have no finishing status"


# --------------------------------------------------------------------------
# Security -- the public key is the only key a browser ever holds
# --------------------------------------------------------------------------

def _write(method: str, resource: str, body=None):
    import json as _json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"{repo.SUPABASE_URL}/rest/v1/{resource}",
        method=method,
        data=_json.dumps(body).encode() if body else None,
        headers={"apikey": repo.SUPABASE_KEY,
                 "Authorization": f"Bearer {repo.SUPABASE_KEY}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_public_read_is_allowed():
    rows, _ = repo.query("drivers", select="display_name", limit=1)
    assert rows


@pytest.mark.parametrize("method,resource,body", [
    ("POST", "drivers", [{"driver_key": "test", "display_name": "Test"}]),
    ("POST", "results", [{"race_id": 1, "driver_id": 1, "constructor_id": 1, "position": 1}]),
    ("PATCH", "results?id=eq.1", {"position": 2}),
    ("DELETE", "results?id=eq.1", None),
    ("POST", "seasons", [{"year": 1999, "display_name": "1999"}]),
])
def test_public_writes_are_blocked(method, resource, body):
    assert _write(method, resource, body) in (401, 403, 404)


def test_staging_is_not_publicly_readable():
    """Staging holds raw, unvalidated source rows. It is server-side only."""
    import urllib.error
    with pytest.raises((repo.SupabaseError, urllib.error.HTTPError)):
        repo.query("staging_results", select="id", limit=1)


def test_api_never_loads_a_key_that_bypasses_rls():
    """The service-role key bypasses Row Level Security. The API layer must
    never read it -- only the ingestion script, server-side."""
    import os
    import pathlib

    module = pathlib.Path(repo.__file__).read_text(encoding="utf-8")
    # os.getenv calls in this module may only reference the two safe names.
    referenced = {
        line.split('os.getenv("')[1].split('"')[0]
        for line in module.splitlines()
        if 'os.getenv("' in line
    }
    assert referenced <= {"SUPABASE_URL", "SUPABASE_ANON_KEY"}, referenced

    # And the key actually in use must not be a secret key.
    assert not repo.SUPABASE_KEY.startswith("sb_secret")
    assert not repo.SUPABASE_KEY.startswith("service_role")
    del os
