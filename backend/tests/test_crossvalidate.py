"""The cross-validator's own logic, without the network.

`crossvalidate` is the only check that can prove the dataset matches something
outside this repository, so its comparison rules have to be right. The fetches
need network and a live API; the rules do not, and those are what silently
decide whether a disagreement is reported or swallowed.
"""
from __future__ import annotations

from backend.etl import crossvalidate


def test_accents_are_not_treated_as_disagreements():
    """"Antonio" and "Antônio" are the same driver.

    Folding is for comparison only. The stored value keeps the source's own
    spelling -- this must never become a reason to normalise the database.
    """
    assert crossvalidate.fold("Antônio Giovinazzi") == crossvalidate.fold("Antonio Giovinazzi")
    assert crossvalidate.fold("Kimi Räikkönen") == crossvalidate.fold("Kimi Raikkonen")
    assert crossvalidate.fold("Jean-Eric Vergne") == crossvalidate.fold("Jean Eric Vergne")


def test_different_drivers_still_compare_as_different():
    """The guard on the test above: folding must not flatten everyone together."""
    assert crossvalidate.fold("Lewis Hamilton") != crossvalidate.fold("Nico Rosberg")
    assert crossvalidate.fold("Michael Schumacher") != crossvalidate.fold("Ralf Schumacher")


def test_a_one_to_one_circuit_mapping_is_clean():
    pairs = {("monza", "monza"), ("spa", "spa"), ("silverstone", "silverstone")}
    assert crossvalidate.circuit_bijection_failures(pairs) == []


def test_naming_differences_alone_are_not_failures():
    """The whole reason this is a bijection and not a name comparison.

    Jolpica says 'albert_park', this project says 'melbourne'. Neither is
    wrong; they are different names for one venue, and a name comparison would
    report 39 discrepancies that are all noise.
    """
    pairs = {("albert_park", "melbourne"), ("villeneuve", "montreal"), ("magny_cours", "magny-cours")}
    assert crossvalidate.circuit_bijection_failures(pairs) == []


def test_a_venue_split_across_two_local_circuits_is_reported():
    """One source circuit reaching two local circuits divides a venue's records."""
    pairs = {("suzuka", "suzuka"), ("suzuka", "suzuka-east")}
    problems = crossvalidate.circuit_bijection_failures(pairs)
    assert len(problems) == 1
    assert "split" in problems[0] and "suzuka" in problems[0]


def test_two_venues_merged_into_one_local_circuit_is_reported():
    """The other direction, and the more dangerous one.

    A merge makes "this driver's record at this circuit" span two different
    tracks, and nothing in the UI would indicate it.
    """
    pairs = {("hockenheimring", "germany"), ("nurburgring", "germany")}
    problems = crossvalidate.circuit_bijection_failures(pairs)
    assert len(problems) == 1
    assert "merges" in problems[0]


def test_the_bahrain_outer_split_is_exempt_and_exactly_that_split():
    """2020 Sakhir ran the Outer Circuit; the local dataset is right to split it.

    The exemption is pinned to the exact pair. A third local circuit appearing
    under 'bahrain' is a new fact and must be reported, not absorbed by an
    exemption written for a different one.
    """
    known = {("bahrain", "bahrain"), ("bahrain", "bahrain-outer")}
    assert crossvalidate.circuit_bijection_failures(known) == []

    drifted = known | {("bahrain", "bahrain-something-else")}
    assert crossvalidate.circuit_bijection_failures(drifted) != []


def test_exempt_splits_name_a_reason_in_the_source():
    """An exemption with no recorded reasoning is how a check quietly dies."""
    source = crossvalidate.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "KNOWN_CONFIGURATION_SPLITS" in text
    assert "Outer Circuit" in text, "the Bahrain exemption must say what it is"
