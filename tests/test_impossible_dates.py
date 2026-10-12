from conftest import clean_one

ACCIDENT_AFTER = "Accident date is after the date received"
BIRTH_AFTER = "Date of birth is after the accident date"


def test_accident_after_received_is_flagged_with_the_reason(conn):
    claim = clean_one(conn, received_date="2025-10-05", accident_date="2025-10-06")
    assert claim["date_problem"] == ACCIDENT_AFTER
    assert claim["status"] == "cleaned"


def test_birth_after_accident_is_flagged_with_the_reason(conn):
    claim = clean_one(conn, date_of_birth="2025-09-01", accident_date="2025-08-15")
    assert claim["date_problem"] == BIRTH_AFTER


def test_both_problems_give_both_reasons(conn):
    claim = clean_one(conn, received_date="2025-10-05", accident_date="2025-10-06",
                      date_of_birth="2025-10-07")
    assert claim["date_problem"] == f"{ACCIDENT_AFTER}; {BIRTH_AFTER}"


def test_accident_on_the_received_date_is_fine(conn):
    claim = clean_one(conn, received_date="2025-10-05", accident_date="2025-10-05")
    assert claim["date_problem"] is None


def test_birth_on_the_accident_date_is_not_flagged(conn):
    claim = clean_one(conn, date_of_birth="2025-08-15", accident_date="2025-08-15")
    assert claim["date_problem"] is None


def test_missing_date_of_birth_is_not_flagged(conn):
    assert clean_one(conn, date_of_birth="")["date_problem"] is None


def test_dates_in_other_formats_are_compared_after_conversion(conn):
    claim = clean_one(conn, received_date="05/10/25", accident_date="2025-10-06")
    assert claim["date_problem"] == ACCIDENT_AFTER


def test_a_no_year_accident_date_is_never_after_the_received_date(conn):
    claim = clean_one(conn, received_date="2025-10-05", accident_date="6th October")
    assert claim["accident_date"] == "2024-10-06"
    assert claim["date_problem"] is None


def test_cleaning_does_not_set_a_route(conn):
    claim = clean_one(conn, accident_date="2025-12-31")
    assert "route" not in claim.keys()
    assert claim["status"] == "cleaned"


def test_rejected_rows_are_not_checked_for_impossible_dates(conn):
    claim = clean_one(conn, claimant_name="", accident_date="2025-12-31")
    assert claim["date_problem"] is None
