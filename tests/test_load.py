import csv

import pytest

import loading
from conftest import ROOT, add_claims, make_raw_claim

CSV_PATH = ROOT / "claim_notifications.csv"


def test_all_csv_rows_load_with_status_loaded(conn):
    assert loading.load_claims(conn, CSV_PATH) == 150
    statuses = {r[0] for r in conn.execute("SELECT status FROM claims")}
    assert statuses == {"loaded"}
    assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 150


def test_raw_values_equal_the_csv_exactly(conn):
    loading.load_claims(conn, CSV_PATH)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        expected = {r["reference"]: r for r in csv.DictReader(f)}
    for raw in conn.execute("SELECT * FROM raw_claims"):
        assert dict(raw) == expected[raw["reference"]]


def test_loading_twice_adds_nothing(conn):
    loading.load_claims(conn, CSV_PATH)
    assert loading.load_claims(conn, CSV_PATH) == 0
    assert conn.execute("SELECT COUNT(*) FROM raw_claims").fetchone()[0] == 150


def test_reload_does_not_overwrite_an_existing_claim(conn):
    add_claims(conn, make_raw_claim(claimant_name="Kate Owen"))
    add_claims(conn, make_raw_claim(claimant_name="Someone Else"))
    name = conn.execute("SELECT claimant_name FROM raw_claims").fetchone()[0]
    assert name == "Kate Owen"


def test_csv_with_a_missing_column_raises_a_clear_error(conn, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("reference,received_date\nFN-1,2025-01-01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing expected columns"):
        loading.load_claims(conn, bad)
