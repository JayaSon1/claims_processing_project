import pytest

import dedupe
from conftest import clean_rows, make_raw_claim


def claim(reference, **overrides):
    return make_raw_claim(reference=reference, **overrides)


def run(conn, *rows):
    clean_rows(conn, *rows)
    dedupe.find_duplicates(conn)
    return {r["reference"]: r for r in conn.execute("SELECT * FROM claims")}


def test_same_dob_accident_date_and_name_is_a_duplicate_linked_to_the_kept_claim(conn):
    claims = run(conn, claim("FN-00001", received_date="2025-10-05"),
                 claim("FN-00004", received_date="2025-10-07", email="other@example.org"))
    assert claims["FN-00001"]["status"] == "cleaned"
    assert claims["FN-00004"]["status"] == "duplicate"
    assert claims["FN-00004"]["duplicate_of"] == "FN-00001"
    assert claims["FN-00001"]["duplicate_of"] is None


@pytest.mark.parametrize("surname", ["Owne", "Oen", "Wen", "Owens", "OWEN"])
def test_surname_typo_with_the_same_email_is_a_duplicate(conn, surname):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name=f"Kate {surname}", received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "duplicate"


def test_different_name_but_same_email_is_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name="Someone Different", received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "duplicate"


def test_same_name_with_a_different_email_is_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", email="new@example.com", received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "duplicate"


def test_email_comparison_ignores_case_and_spaces(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name="Zed Zulu", email="  KATE.OWEN71@example.org ",
                       received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "duplicate"


def test_different_accident_date_is_not_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"), claim("FN-00002", accident_date="2025-08-16"))
    assert claims["FN-00002"]["status"] == "cleaned"


def test_different_date_of_birth_is_not_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"), claim("FN-00002", date_of_birth="1970-07-21"))
    assert claims["FN-00002"]["status"] == "cleaned"


def test_same_dob_and_accident_date_but_different_name_and_email_is_not_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name="Liam Parry", email="liam@example.com"))
    assert claims["FN-00002"]["status"] == "cleaned"


def test_same_surname_but_different_first_name_and_email_is_not_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name="Owen Owen", email="owen@example.com"))
    assert claims["FN-00002"]["status"] == "cleaned"


def test_surname_off_by_two_letters_with_a_different_email_is_not_a_duplicate(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", claimant_name="Kate Ow", email="x@example.com"))
    assert claims["FN-00002"]["status"] == "cleaned"


def test_the_earliest_received_date_is_kept_whatever_the_reference(conn):
    claims = run(conn, claim("FN-00001", received_date="2025-10-07"),
                 claim("FN-00002", received_date="2025-10-05"))
    assert claims["FN-00002"]["status"] == "cleaned"
    assert claims["FN-00001"]["status"] == "duplicate"
    assert claims["FN-00001"]["duplicate_of"] == "FN-00002"


def test_a_received_date_tie_keeps_the_lowest_reference(conn):
    claims = run(conn, claim("FN-00009", received_date="2025-10-05"),
                 claim("FN-00003", received_date="2025-10-05"))
    assert claims["FN-00003"]["status"] == "cleaned"
    assert claims["FN-00009"]["duplicate_of"] == "FN-00003"


def test_dates_are_compared_after_conversion_to_iso(conn):
    claims = run(conn, claim("FN-00001", received_date="05/10/25", accident_date="15th August"),
                 claim("FN-00002", received_date="2025-10-06"))
    assert claims["FN-00001"]["status"] == "cleaned"
    assert claims["FN-00002"]["duplicate_of"] == "FN-00001"


def test_a_chain_of_duplicates_links_to_the_one_claim_kept(conn):
    claims = run(conn,
                 claim("FN-00001", received_date="2025-10-05"),
                 claim("FN-00002", received_date="2025-10-06", claimant_name="Kate Owne"),
                 claim("FN-00003", received_date="2025-10-07", claimant_name="Kate Owne",
                       email="third@example.com"))
    assert claims["FN-00001"]["status"] == "cleaned"
    assert claims["FN-00002"]["duplicate_of"] == "FN-00001"
    assert claims["FN-00003"]["duplicate_of"] == "FN-00001"


def test_rejected_claims_are_ignored_on_both_sides(conn):
    claims = run(conn, claim("FN-00001", accident_description=""),
                 claim("FN-00002", received_date="2025-10-06"),
                 claim("FN-00003", received_date="2025-10-07", accident_description=""))
    assert claims["FN-00001"]["status"] == "rejected"
    assert claims["FN-00002"]["status"] == "cleaned"
    assert claims["FN-00003"]["status"] == "rejected"


def test_blank_dates_of_birth_are_not_merged_but_flagged_both_ways(conn):
    claims = run(conn, claim("FN-00001", date_of_birth=""),
                 claim("FN-00002", date_of_birth="", received_date="2025-10-06"))
    assert claims["FN-00001"]["status"] == "cleaned"
    assert claims["FN-00002"]["status"] == "cleaned"
    assert claims["FN-00001"]["duplicate_review_note"].startswith("Possible duplicate of FN-00002.")
    assert claims["FN-00002"]["duplicate_review_note"].startswith("Possible duplicate of FN-00001.")
    assert "date of birth is missing" in claims["FN-00001"]["duplicate_review_note"].lower()


def test_blank_date_of_birth_against_a_claim_with_one_is_flagged_on_the_blank_one_only(conn):
    claims = run(conn, claim("FN-00001"), claim("FN-00002", date_of_birth="", received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "cleaned"
    assert claims["FN-00002"]["duplicate_review_note"].startswith("Possible duplicate of FN-00001.")
    assert claims["FN-00001"]["duplicate_review_note"] is None


def test_unreadable_date_of_birth_is_treated_like_a_blank_one(conn):
    claims = run(conn, claim("FN-00001"),
                 claim("FN-00002", date_of_birth="last June", received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "cleaned"
    assert claims["FN-00002"]["duplicate_review_note"] is not None


def test_blank_date_of_birth_with_no_likely_match_has_no_note(conn):
    claims = run(conn, claim("FN-00001", date_of_birth=""),
                 claim("FN-00002", accident_date="2025-08-16", received_date="2025-10-06"))
    assert claims["FN-00001"]["duplicate_review_note"] is None


def test_blank_date_of_birth_with_a_different_person_has_no_note(conn):
    claims = run(conn, claim("FN-00001", date_of_birth=""),
                 claim("FN-00002", claimant_name="Liam Parry", email="liam@example.com"))
    assert claims["FN-00001"]["duplicate_review_note"] is None


def test_running_the_duplicate_step_twice_changes_nothing(conn):
    run(conn, claim("FN-00001"), claim("FN-00002", received_date="2025-10-06"),
        claim("FN-00003", date_of_birth="", received_date="2025-10-07"))
    before = [dict(r) for r in conn.execute("SELECT * FROM claims ORDER BY reference")]
    dedupe.find_duplicates(conn)
    after = [dict(r) for r in conn.execute("SELECT * FROM claims ORDER BY reference")]
    assert before == after


def test_a_claim_with_a_one_word_name_matches_only_on_email(conn):
    claims = run(conn, claim("FN-00001", claimant_name="Cher"),
                 claim("FN-00002", claimant_name="Cher", email="other@example.com",
                       received_date="2025-10-06"))
    assert claims["FN-00002"]["status"] == "cleaned"
