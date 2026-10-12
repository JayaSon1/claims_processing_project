import pytest

from cleaning import parse_birth_date, parse_date

RECEIVED = "2025-10-05"


@pytest.mark.parametrize("text, expected", [
    ("2025-04-03", "2025-04-03"),
    ("03/04/25", "2025-04-03"),
    ("  03/04/25  ", "2025-04-03"),
    ("29/02/24", "2024-02-29"),
])
def test_accepted_formats_become_iso(text, expected):
    assert parse_date(text, RECEIVED) == expected


def test_received_date_parses_without_a_reference_date():
    assert parse_date("23/12/25") == "2025-12-23"
    assert parse_date("2026-08-11") == "2026-08-11"


@pytest.mark.parametrize("text, expected", [
    ("3rd April", "2025-04-03"),
    ("1st August", "2025-08-01"),
    ("2nd September", "2025-09-02"),
    ("23rd March", "2025-03-23"),
    ("11th December", "2024-12-11"),
    ("5TH OCTOBER", "2025-10-05"),
    ("16th july", "2025-07-16"),
    (" 4th  May ", "2025-05-04"),
])
def test_dates_with_no_year_use_the_received_year_or_the_year_before(text, expected):
    assert parse_date(text, RECEIVED) == expected


def test_no_year_date_on_the_received_day_stays_in_the_received_year():
    assert parse_date("5th October", RECEIVED) == "2025-10-05"


def test_no_year_date_after_received_uses_the_year_before():
    assert parse_date("6th October", RECEIVED) == "2024-10-06"


def test_31st_december_received_on_1_january_gives_the_previous_year():
    assert parse_date("31st December", "2026-01-01") == "2025-12-31"


def test_29_february_in_a_non_leap_year_is_unreadable():
    assert parse_date("29th February", RECEIVED) is None


def test_29_february_in_a_leap_received_year_is_accepted():
    assert parse_date("29th February", "2028-06-01") == "2028-02-29"


def test_no_year_date_cannot_be_read_without_a_received_date():
    assert parse_date("3rd April") is None


@pytest.mark.parametrize("text", [
    "31/04/25", "2025-02-30", "03/04/2025", "yesterday", "", "   ", None,
    "13/13/25", "3rd Smarch", "April 3rd", "2025/04/03", "3/4/25", "0th April",
])
def test_unreadable_dates_return_none(text):
    assert parse_date(text, RECEIVED) is None


def test_iso_date_of_birth_is_kept():
    assert parse_birth_date("1970-07-20", "2025-08-15") == "1970-07-20"


def test_two_digit_birth_year_is_1900s_for_a_normal_age():
    assert parse_birth_date("15/06/72", "2025-08-15") == "1972-06-15"


def test_two_digit_birth_year_with_age_exactly_100_is_1900s():
    assert parse_birth_date("05/10/25", "2025-10-05") == "1925-10-05"


def test_two_digit_birth_year_with_age_101_is_2000s():
    assert parse_birth_date("05/10/24", "2025-10-05") == "2024-10-05"


def test_two_digit_birth_year_one_day_before_turning_101_is_still_1900s():
    assert parse_birth_date("06/10/24", "2025-10-05") == "1924-10-06"
    assert parse_birth_date("06/10/25", "2025-10-05") == "1925-10-06"


def test_two_digit_birth_year_needs_a_readable_accident_date():
    assert parse_birth_date("15/06/72", None) is None


@pytest.mark.parametrize("text", ["", None, "last June", "3rd April", "31/02/80"])
def test_unreadable_birth_dates_return_none(text):
    assert parse_birth_date(text, "2025-08-15") is None
