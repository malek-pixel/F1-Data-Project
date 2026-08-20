"""API tests: valid requests, invalid input, empty results, missing entities."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import analytics
from backend.app.db import DB_PATH
from backend.app.main import app

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="database not built -- run: python -m backend.etl.build"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_states_data_is_not_live(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["live_data"] is False
    assert body["season_to"] == 2025


def test_driver_list_paginates(client):
    body = client.get("/api/drivers?limit=5").json()
    assert body["total"] == 129
    assert len(body["items"]) == 5
    assert body["items"][0]["wins"] >= body["items"][1]["wins"]


def test_driver_search_filters_server_side(client):
    body = client.get("/api/drivers?search=Hamilton").json()
    assert body["total"] == 1
    assert "Hamilton" in body["items"][0]["name"]


def test_search_with_no_matches_returns_empty_not_error(client):
    body = client.get("/api/drivers?search=zzzznotadriver").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_unknown_sort_key_is_rejected(client):
    assert client.get("/api/drivers?sort=points").status_code == 422


def test_out_of_range_limit_is_rejected(client):
    assert client.get("/api/drivers?limit=0").status_code == 422
    assert client.get("/api/drivers?limit=9999").status_code == 422


def test_missing_driver_returns_404_with_structured_detail(client):
    response = client.get("/api/drivers/999999")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_driver_detail_includes_constructor_history(client):
    body = client.get("/api/drivers/1").json()
    assert set(body) == {
        "id", "slug", "name", "nationality", "date_of_birth",
        "abbreviation", "permanent_number", "stats", "constructors",
    }
    assert body["stats"]["entries"] > 0


def test_entities_resolve_by_slug_and_legacy_id_identically(client):
    """The slug and the integer id must address the same row.

    This is the invariant the slug exists to provide. Integer ids are assigned
    by each store independently, so they are not portable; the slug is. If
    these two payloads ever diverge, a link built from one key space is
    silently resolving to a different entity in the other.
    """
    for kind in ("drivers", "constructors", "circuits"):
        by_id = client.get(f"/api/{kind}/1").json()
        slug = by_id["slug"]
        assert slug, f"{kind}/1 has no slug"
        by_slug = client.get(f"/api/{kind}/{slug}").json()
        assert by_slug == by_id


def test_unknown_slug_is_404_not_a_server_error(client):
    assert client.get("/api/drivers/no-such-driver").status_code == 404


def test_list_endpoints_expose_the_portable_identifier(client):
    """Every listed entity must carry `slug`, not just `id`.

    Worth asserting because the failure mode is silent: a response_model
    without the field drops it during serialisation, so the SQL can select it,
    the handler can return it, and the client still never sees it. That is
    exactly how it broke once. A client that cannot get a slug from a list has
    to fall back to the non-portable integer id.
    """
    for kind in ("drivers", "constructors"):
        items = client.get(f"/api/{kind}?limit=5").json()["items"]
        assert items, f"/api/{kind} returned nothing"
        assert all(item.get("slug") for item in items), f"/api/{kind} items lack slug"

    contributions = client.get("/api/constructors/1/drivers").json()
    assert all(row.get("driver_slug") for row in contributions)


def test_no_computed_stat_is_dropped_before_it_reaches_the_client(client):
    """What analytics computes is what the API serves.

    A response_model silently discards keys it does not declare. That is a
    failure with no symptom: the query runs, the handler returns the value,
    the test suite stays green, and the field is simply missing from the
    payload. It had already happened to ten fields -- points, dnfs, avg_grid,
    positions gained, top5/top10 and their rates -- so the ingested points and
    finishing-status data was being computed on every request and thrown away.

    Comparing the two directly is the only check that catches it, because
    every layer in isolation looks correct.
    """
    from backend.app import analytics
    from backend.app.db import connect

    conn = connect()
    try:
        computed = analytics.leaderboard(conn, "driver", limit=1)["items"][0]
    finally:
        conn.close()

    served = client.get("/api/drivers?limit=1").json()["items"][0]
    assert set(computed) - set(served) == set()


def test_driver_seasons_are_ordered(client):
    seasons = [s["season"] for s in client.get("/api/drivers/1/seasons").json()]
    assert seasons == sorted(seasons)


def test_constructor_driver_contribution_shares_sum_to_one(client):
    rows = client.get("/api/constructors/1/drivers").json()
    assert sum(r["entry_share"] for r in rows) == pytest.approx(1.0)


def test_circuits_expose_map_availability(client):
    circuits = client.get("/api/circuits").json()
    assert len(circuits) == 39
    assert any(c["has_map"] for c in circuits)
    assert any(not c["has_map"] for c in circuits)


def test_circuit_detail_lists_winners(client):
    body = client.get("/api/circuits/1").json()
    assert body["winners"]
    assert body["top_drivers"]


def test_season_detail_is_labelled_wins_based(client):
    body = client.get("/api/seasons/2021").json()
    assert body["ranking_basis"] == "wins"
    assert body["races"] == 22
    assert len(body["races_list"]) == 22


def test_unknown_season_returns_404(client):
    assert client.get("/api/seasons/1990").status_code == 404


def test_race_detail_returns_full_classification(client):
    body = client.get("/api/races/1").json()
    positions = [r["position"] for r in body["results"]]
    assert positions == sorted(positions)
    assert positions[0] == 1


def test_compare_rejects_identical_entities(client):
    assert client.get("/api/compare/drivers?left=1&right=1").status_code == 400


def test_compare_returns_both_sides_and_methodology(client):
    body = client.get("/api/compare/drivers?left=1&right=2").json()
    assert "left" in body and "right" in body
    assert body["methodology"]


def test_compare_unknown_entity_type_is_rejected(client):
    assert client.get("/api/compare/cars?left=1&right=2").status_code == 422


def test_records_carry_methodology(client):
    records = client.get("/api/records").json()["records"]
    assert records
    assert all(r["methodology"] for r in records)


def test_insights_are_traceable_to_a_query(client):
    insights = client.get("/api/insights").json()["insights"]
    assert insights
    assert all(i["basis"] for i in insights)


def test_dataset_summary_availability_matches_the_database(client):
    """Availability must be measured, never asserted.

    This test used to require "championship points" in `unavailable_fields`,
    which was correct until points were ingested and then became a lie the API
    served to users -- the UI renders this list under "What this dataset cannot
    tell you". The list is now derived from row counts, and this checks the
    derivation against the database rather than against a remembered state.
    """
    body = client.get("/api/dataset/summary").json()
    available = " ".join(body["available_fields"])
    unavailable = body["unavailable_fields"]

    # Ingested, so each must be advertised as available.
    #
    # The last four joined this list after the lap, practice and fastest-lap
    # ingestions. They were in the "must stay declared absent" check below --
    # this test asserted that the API keep calling them unavailable, which is
    # how the exact failure its own docstring describes happened a second
    # time, in the file written to prevent it.
    for field in ("championship points", "finishing status", "grid position",
                  "qualifying", "sprint results", "pit stops",
                  "fastest lap", "race lap times", "sector times", "tyre compounds"):
        assert field in available, f"{field} is ingested but not advertised"
        assert field not in unavailable

    # No source supplies these anywhere, so they must stay declared absent.
    # `cars` is empty by design; if it is ever filled, the probe stops
    # claiming otherwise and this assertion is what will say so.
    for field in ("telemetry", "car specifications"):
        assert field in unavailable

    # And nothing may be called unavailable while rows exist for it.
    from backend.app.db import connect

    conn = connect()
    populated = {
        "championship points": "SELECT COUNT(points) FROM results",
        "finishing status (DNF / DNS / DSQ)": "SELECT COUNT(classification) FROM results",
        "pit stops": "SELECT COUNT(*) FROM pit_stops",
        "qualifying": "SELECT COUNT(*) FROM qualifying_results",
        "fastest lap": "SELECT COUNT(fastest_lap_time) FROM results",
        "race lap times": "SELECT COUNT(*) FROM lap_times",
        "sector times": "SELECT COUNT(sector1) FROM practice_laps",
        "tyre compounds": "SELECT COUNT(compound) FROM practice_laps",
    }
    try:
        for field, sql in populated.items():
            if conn.execute(sql).fetchone()[0]:
                assert field not in unavailable, f"{field} has rows but is declared unavailable"
    finally:
        conn.close()

    assert body["known_issues"]
    # No filesystem paths or connection details leak to the client.
    assert "f1.db" not in str(body)


def test_hidden_constructors_are_withheld_from_browsable_lists(client):
    """Hidden means "not offered to browse", never "deleted"."""
    listed = {row["name"] for row in client.get("/api/constructors?limit=100").json()["items"]}
    assert listed.isdisjoint(analytics.HIDDEN_CONSTRUCTORS)

    teams = {t["constructor_name"] for t in client.get("/api/cars").json()["teams"]}
    assert teams.isdisjoint(analytics.HIDDEN_CONSTRUCTORS)

    hits = client.get("/api/search?q=Benetton").json()["results"]
    assert not [h for h in hits if h["kind"] == "constructor"]


def test_hidden_constructors_still_count_in_every_aggregate(client):
    """The seasons they raced in must be unchanged -- this hides, it never deletes."""
    # An active team: 2025 is incomplete without it.
    names_2025 = {c["name"] for c in client.get("/api/seasons/2025").json()["constructors"]}
    assert "RB F1 Team" in names_2025

    names_2000 = {c["name"] for c in client.get("/api/seasons/2000").json()["constructors"]}
    assert {"BAR", "Benetton"} <= names_2000

    # And their pages still resolve, so a race classification can link to them.
    assert client.get("/api/constructors/6").status_code == 200


def test_car_library_groups_constructor_seasons(client):
    body = client.get("/api/cars").json()
    assert body["chassis_available"] is False, "the source has no chassis column; do not claim otherwise"
    team = body["teams"][0]
    assert team["cars"], "every listed team must have at least one constructor-season"
    seasons = [car["season"] for car in team["cars"]]
    assert seasons == sorted(seasons, reverse=True), "cars run newest first"
    assert team["seasons"] == len(team["cars"])
    assert {car["era"] for car in team["cars"]} <= {"current", "recent", "retired"}


def test_global_search_spans_entity_types(client):
    results = client.get("/api/search?q=Ferrari").json()["results"]
    assert any(r["kind"] == "constructor" for r in results)


def test_global_search_finds_races_by_season_and_venue(client):
    """"2004 monza" is a season filter plus a venue, not one literal string."""
    results = client.get("/api/search?q=2004 monza").json()["results"]
    races = [r for r in results if r["kind"] == "race"]
    assert races, "a season + venue query should reach the race index"
    assert all(r["label"].startswith("2004") for r in races)
    # The bare year still resolves to the season itself.
    assert any(r["kind"] == "season" and r["label"] == "2004" for r in results)


def test_search_requires_a_query(client):
    assert client.get("/api/search?q=").status_code == 422


# --------------------------------------------------------------------------
# Advanced analytics
# --------------------------------------------------------------------------

def test_metric_registry_publishes_definitions_and_thresholds(client):
    body = client.get("/api/analytics/metrics").json()
    assert body["thresholds"]["min_shared_races"] > 0
    keys = {m["key"] for m in body["metrics"]}
    assert {"teammate_h2h", "position_stdev", "circuit_specialism"} <= keys
    assert all(m["limitations"] for m in body["metrics"])


def test_teammates_returns_spells_and_methodology(client):
    body = client.get("/api/drivers/1/teammates").json()
    assert set(body) == {"summary", "spells", "methodology"}
    # The retirement caveat must travel with the numbers.
    assert "retirement" in body["methodology"]["limitations"].lower()


def test_teammate_spells_reconcile(client):
    for spell in client.get("/api/drivers/1/teammates").json()["spells"]:
        assert spell["ahead"] + spell["behind"] == spell["shared_races"]
        assert 0 <= spell["h2h_rate"] <= 1


def test_teammates_404_for_unknown_driver(client):
    assert client.get("/api/drivers/999999/teammates").status_code == 404


def test_distribution_histogram_partitions_entries(client):
    body = client.get("/api/drivers/1/distribution").json()
    assert sum(b["count"] for b in body["histogram"]) == body["entries"]


def test_distribution_scoped_to_a_season_is_smaller(client):
    career = client.get("/api/drivers/1/distribution").json()["entries"]
    season = client.get("/api/drivers/1/distribution?season=2010").json()["entries"]
    assert season <= career


def test_driver_circuits_flag_the_threshold(client):
    body = client.get("/api/drivers/1/circuits").json()
    assert body["min_appearances"] >= 1
    assert all("meets_threshold" in c for c in body["circuits"])


def test_circuit_specialists_honour_min_appearances(client):
    loose = client.get("/api/circuits/1/specialists?min_appearances=1").json()["specialists"]
    strict = client.get("/api/circuits/1/specialists?min_appearances=10").json()["specialists"]
    assert len(strict) <= len(loose)
    assert all(s["appearances"] >= 10 for s in strict)


def test_specialists_reject_out_of_range_threshold(client):
    assert client.get("/api/circuits/1/specialists?min_appearances=0").status_code == 422


def test_season_dominance_is_win_based(client):
    body = client.get("/api/seasons/2023/dominance").json()
    assert body["races"] == 22
    assert 0 < body["top_driver_win_share"] <= 1
    assert "points" in body["basis"].lower()


def test_dominance_404_for_unknown_season(client):
    assert client.get("/api/seasons/1990/dominance").status_code == 404


def test_dominance_timeline_spans_the_dataset(client):
    seasons = client.get("/api/analytics/dominance").json()["seasons"]
    assert len(seasons) == 26
    assert all(0 <= s["top_driver_win_share"] <= 1 for s in seasons)


def test_eras_are_described_not_ranked(client):
    body = client.get("/api/analytics/eras").json()
    assert len(body["eras"]) == 3  # 2000s, 2010s, 2020s
    assert "not as a ranking" in body["caveat"]


def test_insights_span_multiple_categories(client):
    insights = client.get("/api/insights?limit=12").json()["insights"]
    kinds = {i["kind"] for i in insights}
    assert len(kinds) >= 4, f"expected varied insight categories, got {kinds}"
    assert all(i["basis"] for i in insights)


def test_insights_avoid_causal_language(client):
    """The dataset holds no explanatory variables, so no insight may assert a
    cause. Guards against a future generator phrasing a result as an
    explanation."""
    banned = (" because ", " caused ", " proves ", " guaranteed ", " due to ")
    for insight in client.get("/api/insights?limit=12").json()["insights"]:
        text = f" {insight['headline']} {insight['detail']} ".lower()
        assert not any(word in text for word in banned), insight["headline"]


def test_every_linkable_payload_carries_a_slug(client):
    """Anywhere the UI renders a link, the portable identifier must be present.

    Without it a client has no choice but to build the link from the integer
    id, which is store-local: the same URL resolves to a different driver
    depending on which backend produced it. Race classifications, the
    round-by-round strip and circuit winners were all missing it, so every
    link on those pages was necessarily built from the wrong key.
    """
    race_id = client.get("/api/races?limit=1").json()[0]["id"]

    results = client.get(f"/api/races/{race_id}").json()["results"]
    assert results, "race has no classification"
    assert all(row.get("driver_slug") and row.get("constructor_slug") for row in results)

    season = client.get("/api/seasons").json()[0]["season"]
    rounds = client.get(f"/api/seasons/{season}/rounds").json()["rounds"]
    winners = [r for r in rounds if r.get("winner_driver_id") is not None]
    assert winners, "no round has a recorded winner"
    assert all(r.get("winner_driver_slug") for r in winners)

    circuit = client.get("/api/circuits").json()[0]
    detail = client.get(f"/api/circuits/{circuit['slug']}").json()
    assert detail["winners"], "circuit has no winners"
    assert all(w.get("driver_slug") for w in detail["winners"])


def test_race_list_winner_slug_and_id_are_null_together(client):
    """A race with no recorded winner must have neither, never one of the two.

    They come from the same LEFT JOIN, so a slug present without an id (or the
    reverse) would mean the join changed shape and one of the two columns is
    being read from the wrong row.
    """
    for race in client.get("/api/races?limit=200").json():
        assert (race["winner_driver_id"] is None) == (race["winner_driver_slug"] is None)
        assert (race["winner_constructor_id"] is None) == (race["winner_constructor_slug"] is None)


ENTITY_SUBRESOURCES = [
    "/api/drivers/{driver}/seasons",
    "/api/drivers/{driver}/distribution",
    "/api/drivers/{driver}/qualifying",
    "/api/drivers/{driver}/teammates",
    "/api/drivers/{driver}/circuits",
    "/api/constructors/{constructor}/drivers",
    "/api/constructors/{constructor}/distribution",
    "/api/circuits/{circuit}/specialists",
]


@pytest.mark.parametrize("template", ENTITY_SUBRESOURCES)
def test_every_entity_subresource_accepts_a_slug(client, template):
    """A slug must work everywhere an entity is addressed, not just on detail routes.

    Six of these took `driver_id: int` and returned 422 for a slug long after
    the detail routes had been converted, so `/drivers/hamilton` worked while
    `/drivers/hamilton/qualifying` did not. Nothing caught it because each
    route was correct in isolation; only addressing the whole set the same way
    reveals the gap.
    """
    path = template.format(driver="hamilton", constructor="ferrari", circuit="monza")
    assert client.get(path).status_code == 200, f"{path} rejects a slug"


@pytest.mark.parametrize("template", ENTITY_SUBRESOURCES)
def test_slug_and_legacy_id_return_the_same_subresource(client, template):
    """Old numeric links must keep resolving to the same entity.

    Integer ids are still in circulation. They are accepted, not preferred --
    and if the two key spaces ever disagreed, a bookmark would silently open a
    different driver's page.
    """
    ids = {
        "hamilton": client.get("/api/drivers/hamilton").json()["id"],
        "ferrari": client.get("/api/constructors/ferrari").json()["id"],
        "monza": client.get("/api/circuits/monza").json()["id"],
    }
    by_slug = client.get(template.format(driver="hamilton", constructor="ferrari", circuit="monza"))
    by_id = client.get(
        template.format(driver=ids["hamilton"], constructor=ids["ferrari"], circuit=ids["monza"])
    )
    assert by_slug.status_code == by_id.status_code == 200
    assert by_slug.json() == by_id.json()


# ---------------------------------------------------------------------------
# Oversized integers in URLs
#
# A number wider than SQLite's signed 64-bit integer used to reach the driver
# and raise OverflowError. That is not sqlite3.Error, so the API's database
# handler never caught it and the request died as a bare 500 with no `detail`
# body -- the one shape the client cannot render, and one it would offer to
# retry forever because it classifies 5xx as retryable.
#
# Nothing here asserts a specific 404-vs-422 split: both are correct refusals
# and which one applies depends on whether the id is a path segment or a
# bounded query parameter. What must hold is that no such URL reaches 5xx and
# that every refusal still carries `detail`.
# ---------------------------------------------------------------------------

OVERSIZED = "9" * 25

OVERSIZED_URLS = [
    f"/api/drivers/{OVERSIZED}",
    f"/api/drivers/{OVERSIZED}/seasons",
    f"/api/constructors/{OVERSIZED}",
    f"/api/constructors/{OVERSIZED}/drivers",
    f"/api/circuits/{OVERSIZED}",
    f"/api/races/{OVERSIZED}",
    f"/api/seasons/{OVERSIZED}",
    f"/api/seasons/{OVERSIZED}/rounds",
    f"/api/seasons/{OVERSIZED}/standings",
    f"/api/seasons/{OVERSIZED}/dominance",
    f"/api/races?circuit_id={OVERSIZED}",
    f"/api/drivers?constructor_id={OVERSIZED}",
    f"/api/drivers?min_entries={OVERSIZED}",
]


@pytest.mark.parametrize("url", OVERSIZED_URLS)
def test_oversized_id_is_refused_not_crashed(client, url):
    response = client.get(url)
    assert response.status_code in (404, 422), f"{url} -> {response.status_code}"
    assert "detail" in response.json()


def test_ordinary_ids_and_slugs_still_resolve(client):
    """Guards the bound itself: a real id must not be caught by it."""
    assert client.get("/api/drivers/48").status_code == 200
    assert client.get("/api/drivers/hamilton").status_code == 200
    assert client.get("/api/races/1").status_code == 200
    assert client.get("/api/seasons/2021").status_code == 200
    assert client.get("/api/races?circuit_id=1").status_code == 200


# ---------------------------------------------------------------------------
# Championship reconciliation
#
# Constructor standings are summed from race results, and a championship
# penalty is applied to the championship rather than to the results. Summing
# alone therefore named McLaren the 2007 constructors' champion, which is
# false. These cases pin the two seasons where derivation and record diverge,
# plus unpenalised seasons on either side so the correction cannot quietly
# start applying where it does not belong.
# ---------------------------------------------------------------------------

OFFICIAL_CONSTRUCTOR_POINTS = {
    # (season, constructor name): official final championship points
    (2007, "Ferrari"): 204.0,
    (2007, "McLaren"): 0.0,       # excluded; scored 218
    (2007, "BMW Sauber"): 101.0,
    (2020, "Mercedes"): 573.0,
    (2020, "Racing Point"): 195.0,  # 210 scored, 15 deducted
    (2020, "Renault"): 181.0,
    (2009, "Brawn"): 172.0,
    (2021, "Mercedes"): 613.5,
    (2024, "McLaren"): 666.0,
}


@pytest.mark.parametrize("key,expected", sorted(OFFICIAL_CONSTRUCTOR_POINTS.items()))
def test_constructor_points_match_official(client, key, expected):
    season, name = key
    table = client.get(f"/api/seasons/{season}/standings").json()["constructors"]
    row = next((r for r in table if r["name"] == name), None)
    assert row is not None, f"{name} missing from {season} constructors"
    assert row["points"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "season,champion",
    [(2007, "Ferrari"), (2009, "Brawn"), (2020, "Mercedes"), (2024, "McLaren")],
)
def test_constructor_champion_is_the_real_one(client, season, champion):
    table = client.get(f"/api/seasons/{season}/standings").json()["constructors"]
    assert table[0]["name"] == champion


def test_penalty_is_visible_not_silent(client):
    """A total that was reduced must say so, and must not lose the races won."""
    table = client.get("/api/seasons/2007/standings").json()["constructors"]
    mclaren = next(r for r in table if r["name"] == "McLaren")
    assert mclaren["points"] == 0.0
    assert mclaren["wins"] == 8, "the exclusion removed points, not race wins"
    penalty = mclaren["penalty"]
    assert penalty["excluded"] is True
    assert penalty["points_scored"] == 218.0
    assert penalty["reason"] and penalty["evidence"]


def test_unpenalised_seasons_carry_no_penalty_field(client):
    table = client.get("/api/seasons/2024/standings").json()["constructors"]
    assert all("penalty" not in row for row in table)


def test_driver_standings_are_untouched_by_constructor_penalties(client):
    """2007 driver points were explicitly unaffected by McLaren's exclusion."""
    drivers = client.get("/api/seasons/2007/standings").json()["drivers"]
    assert drivers[0]["name"].endswith("Räikkönen")
    assert drivers[0]["points"] == pytest.approx(110.0)
    assert [d["points"] for d in drivers[1:3]] == [pytest.approx(109.0), pytest.approx(109.0)]


def test_health_fails_when_the_active_store_is_down(monkeypatch):
    """A health check that cannot fail is not a health check.

    This endpoint used to read SQLite unconditionally, so under
    F1_BACKEND=supabase with Supabase unreachable it answered 200 "ok" while
    every real route answered 503. docs/OPERATIONS.md § 6 names an uptime
    check on /api/health as the first monitoring to add, which would have made
    that discrepancy the difference between an outage and a silent one.

    The client must still see only the safe message -- no host, no driver
    error, no stack.
    """
    from backend.app import backends, supabase_repo

    monkeypatch.setenv("F1_BACKEND", "supabase")
    monkeypatch.setattr(supabase_repo, "configured", lambda: True)

    def unreachable(*_args, **_kwargs):
        raise supabase_repo.SupabaseError("connection refused")

    monkeypatch.setattr(supabase_repo, "query", unreachable)
    supabase_repo.clear_cache()

    assert backends.selected() == "supabase"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Data store unavailable. Retry shortly."
    # Nothing else leaks. `request_id` is the only companion key, and it is a
    # token this process minted -- not host, driver error, or stack.
    assert set(body) == {"detail", "request_id"}
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_health_reports_the_same_coverage_from_whichever_store_answers(client):
    """The payload shape must not depend on the backend.

    `Health` in frontend/src/types.ts declares every field non-optional,
    including `circuits_with_map`. A store that omitted one would typecheck
    and then render "undefined of 39 circuits" to a reader.
    """
    from backend.app import supabase_repo

    if not supabase_repo.configured():
        pytest.skip("SUPABASE_URL / SUPABASE_ANON_KEY unset -- parity unproven")

    local = client.get("/api/health").json()
    remote = supabase_repo.health()
    shared = (
        "season_from", "season_to", "seasons", "races", "results",
        "drivers", "constructors", "circuits", "circuits_with_map", "live_data",
    )
    for field in shared:
        assert field in remote, f"supabase health omits {field}"
        assert remote[field] == local[field], (
            f"{field}: supabase {remote[field]} vs sqlite {local[field]}"
        )
