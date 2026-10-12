import pytest

from conftest import add_claims, clean_one, clean_rows, make_raw_claim

REQUIRED = ["reference", "received_date", "claimant_name", "accident_date", "accident_description"]
OPTIONAL = ["date_of_birth", "road_user_type", "vehicle_registrations", "other_driver_insurer"]


@pytest.mark.parametrize("field", REQUIRED[1:])
def test_blank_required_field_sets_the_claim_aside_with_a_reason(conn, field):
    claim = clean_one(conn, **{field: ""})
    assert claim["status"] == "rejected"
    assert claim["reject_reason"] == f"Missing required field: {field}"


def test_blank_reference_is_set_aside(conn):
    claim = clean_rows(conn, make_raw_claim(reference=""))[""]
    assert claim["status"] == "rejected"
    assert "reference" in claim["reject_reason"]


@pytest.mark.parametrize("field", REQUIRED[1:])
def test_whitespace_only_required_field_counts_as_missing(conn, field):
    claim = clean_one(conn, **{field: "  \t "})
    assert claim["status"] == "rejected"
    assert claim["reject_reason"] == f"Missing required field: {field}"


@pytest.mark.parametrize("field", ["received_date", "accident_date"])
def test_unreadable_required_date_sets_the_claim_aside(conn, field):
    claim = clean_one(conn, **{field: "last Tuesday"})
    assert claim["status"] == "rejected"
    assert claim["reject_reason"] == f"Unreadable required date: {field}"


def test_accident_date_with_no_year_is_unreadable_if_received_date_is(conn):
    claim = clean_one(conn, received_date="soon", accident_date="3rd April")
    assert claim["status"] == "rejected"
    assert claim["reject_reason"] == (
        "Unreadable required date: received_date; Unreadable required date: accident_date")


def test_several_problems_give_one_combined_reason(conn):
    claim = clean_one(conn, claimant_name="", accident_date="")
    assert claim["reject_reason"] == (
        "Missing required field: claimant_name; Missing required field: accident_date")


@pytest.mark.parametrize("field", OPTIONAL)
def test_blank_optional_field_does_not_cause_rejection(conn, field):
    claim = clean_one(conn, **{field: ""})
    assert claim["status"] == "cleaned"
    assert claim["reject_reason"] is None


def test_unreadable_date_of_birth_is_not_rejected_but_noted(conn):
    claim = clean_one(conn, date_of_birth="last June")
    assert claim["status"] == "cleaned"
    assert claim["date_of_birth"] is None
    assert claim["cleaning_note"] == "Date of birth could not be read"


def test_blank_date_of_birth_has_no_cleaning_note(conn):
    assert clean_one(conn, date_of_birth="")["cleaning_note"] is None


def test_valid_row_becomes_cleaned_with_no_reason(conn):
    claim = clean_one(conn)
    assert claim["status"] == "cleaned"
    assert claim["reject_reason"] is None


def test_rejected_row_keeps_its_raw_record(conn):
    clean_one(conn, claimant_name="", phone="07700 900001")
    raw = conn.execute("SELECT * FROM raw_claims").fetchone()
    assert raw["claimant_name"] == "" and raw["phone"] == "07700 900001"


def test_good_rows_are_unaffected_by_a_rejected_row(conn):
    claims = clean_rows(conn, make_raw_claim(reference="FN-00001", accident_date=""),
                        make_raw_claim(reference="FN-00002"))
    assert claims["FN-00001"]["status"] == "rejected"
    assert claims["FN-00002"]["status"] == "cleaned"
