"""Step 1 checked against the real 150-row CSV (SPEC section 14, first acceptance tests)."""
import csv
import hashlib
import re
from collections import defaultdict

import pytest

import dedupe
import prepare_claims
from conftest import ROOT

CSV_PATH = ROOT / "claim_notifications.csv"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
POSTCODE = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]? \d[A-Z]{2}$")
UK_PLATE = re.compile(r"^[A-Z]{2}\d{2} [A-Z]{3}$")
FOREIGN_PLATE = re.compile(r"^[A-Z]{2}-\d{3}-[A-Z]{2}$")

# Fingerprints of the files this step must not change.
CSV_SHA256 = "85151ad7727749d54c64be226be091fff287bac472ae1716c2e251da9d1a09ce"
GENERATOR_SHA256 = "fed227f2a19a432b48e07d9bc2c70098062b960d4c26b6f9e53ecd209c60ed58"


@pytest.fixture
def prepared(conn):
    prepare_claims.prepare_claims(conn, CSV_PATH)
    return conn


def all_claims(conn):
    return {r["reference"]: r for r in conn.execute("SELECT * FROM claims")}


def expected_duplicate_pairs():
    """Pairs found the way generate_claims.py validates them: same date, place and description."""
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        groups = defaultdict(list)
        for row in csv.DictReader(f):
            key = (row["accident_date"], row["accident_location"], row["accident_description"])
            groups[key].append(row)
    pairs = {}
    for group in groups.values():
        if len(group) == 2:
            kept, later = sorted(group, key=lambda r: (r["reference"]))
            pairs[later["reference"]] = kept["reference"]
    return pairs


def test_all_150_rows_load_and_none_are_rejected(prepared):
    claims = all_claims(prepared)
    assert len(claims) == 150
    assert not [c for c in claims.values() if c["status"] == "rejected"]


def test_dates_postcodes_and_plates_are_in_the_cleaned_formats(prepared):
    for c in all_claims(prepared).values():
        for field in ("received_date", "accident_date"):
            assert ISO.match(c[field]), (c["reference"], field, c[field])
        assert c["date_of_birth"] is None or ISO.match(c["date_of_birth"])
        assert POSTCODE.match(c["postcode"]), (c["reference"], c["postcode"])
        for plate in (c["claimant_vehicle"], c["other_vehicle"]):
            assert plate is None or UK_PLATE.match(plate) or FOREIGN_PLATE.match(plate), \
                (c["reference"], plate)


def test_the_six_duplicate_pairs_are_merged_and_nothing_else(prepared):
    merged = {r["reference"]: r["duplicate_of"] for r in prepared.execute(
        "SELECT reference, duplicate_of FROM claims WHERE status = 'duplicate'")}
    assert len(expected_duplicate_pairs()) == 6
    assert merged == expected_duplicate_pairs()


def test_144_claims_remain_cleaned_and_kept_claims_are_untouched(prepared):
    claims = all_claims(prepared)
    assert sum(c["status"] == "cleaned" for c in claims.values()) == 144
    for kept in set(expected_duplicate_pairs().values()):
        assert claims[kept]["status"] == "cleaned"


def test_claims_with_the_accident_after_receipt_have_a_date_problem(prepared):
    flagged = {r["reference"] for r in prepared.execute(
        "SELECT reference FROM claims WHERE date_problem IS NOT NULL")}
    assert flagged == {"FN-00003", "FN-00070", "FN-00077"}
    for c in all_claims(prepared).values():
        assert (c["accident_date"] > c["received_date"]) == (c["reference"] in flagged)


def test_accident_dates_written_without_a_year_become_iso(prepared):
    claims = all_claims(prepared)
    assert claims["FN-00037"]["accident_date"] == "2025-12-11"
    assert claims["FN-00122"]["accident_date"] == "2026-07-16"
    assert claims["FN-00130"]["accident_date"] == "2026-07-13"


def test_slash_dates_become_iso(prepared):
    claims = all_claims(prepared)
    assert claims["FN-00037"]["received_date"] == "2025-12-23"
    assert claims["FN-00130"]["received_date"] == "2026-08-25"


def test_no_blank_date_of_birth_is_merged_and_none_needed_a_review_note(prepared):
    blank = [c for c in all_claims(prepared).values() if c["date_of_birth"] is None]
    assert blank
    assert all(c["status"] == "cleaned" for c in blank)
    assert all(c["duplicate_review_note"] is None for c in blank)


def test_running_the_whole_step_twice_gives_identical_results(prepared):
    before = [dict(r) for r in prepared.execute("SELECT * FROM claims ORDER BY reference")]
    assert prepare_claims.prepare_claims(prepared, CSV_PATH) == 0
    dedupe.find_duplicates(prepared)
    after = [dict(r) for r in prepared.execute("SELECT * FROM claims ORDER BY reference")]
    assert before == after


@pytest.mark.parametrize("name, expected", [
    ("claim_notifications.csv", CSV_SHA256),
    ("generate_claims.py", GENERATOR_SHA256),
])
def test_the_input_files_are_unchanged(name, expected):
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
