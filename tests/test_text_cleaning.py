import pytest

import cleaning
from cleaning import split_name, split_registrations
from conftest import clean_one, clean_rows, make_raw_claim

TEXT_FIELDS = ["claimant_name", "phone", "email", "accident_location",
               "road_user_type", "other_driver_insurer", "accident_description",
               "injuries_described", "time_off_work"]


@pytest.mark.parametrize("field", TEXT_FIELDS)
def test_text_fields_are_trimmed(conn, field):
    value = make_raw_claim()[field]
    claim = clean_one(conn, **{field: f"   {value}\t "})
    assert claim[field] == value


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_blank_optional_text_is_stored_as_null(conn, blank):
    claim = clean_one(conn, other_driver_insurer=blank, road_user_type=blank)
    assert claim["other_driver_insurer"] is None
    assert claim["road_user_type"] is None


@pytest.mark.parametrize("raw, expected", [
    ("ch14bq", "CH1 4BQ"),
    ("ch1  4bq", "CH1 4BQ"),
    ("CH65 7HX", "CH65 7HX"),
    ("l36 6lf", "L36 6LF"),
    ("m1 1aa", "M1 1AA"),
    ("CH14BQ", "CH1 4BQ"),
    ("  ch1 4bq ", "CH1 4BQ"),
    ("ab1", "AB1"),
])
def test_postcodes_are_uppercase_with_one_space_before_the_last_three(conn, raw, expected):
    assert clean_one(conn, postcode=raw)["postcode"] == expected


def test_blank_postcode_stays_null(conn):
    assert clean_one(conn, postcode="")["postcode"] is None


@pytest.mark.parametrize("raw", ["ab15cde", "AB 15 CDE", "AB15CDE", "ab15 cde", "  AB15 CDE "])
def test_uk_plates_become_the_standard_format(conn, raw):
    registrations = f"Claimant vehicle: {raw}; Other vehicle: {raw}"
    claim = clean_one(conn, vehicle_registrations=registrations)
    assert claim["claimant_vehicle"] == "AB15 CDE"
    assert claim["other_vehicle"] == "AB15 CDE"


@pytest.mark.parametrize("raw, expected", [
    ("HP 24 FFF", "HP24 FFF"), ("lw21 lab", "LW21 LAB"), ("VV68SOR", "VV68 SOR"),
    ("pb74 omd", "PB74 OMD"), ("LR71LVO", "LR71 LVO"),
])
def test_messy_plates_from_the_data_are_fixed(conn, raw, expected):
    claim = clean_one(conn, vehicle_registrations=f"Other vehicle: {raw}")
    assert claim["other_vehicle"] == expected


@pytest.mark.parametrize("raw", ["KC-807-MD", "kc-807-md"])
def test_foreign_format_plates_keep_their_hyphens(conn, raw):
    claim = clean_one(conn, vehicle_registrations=f"Other vehicle: {raw}")
    assert claim["other_vehicle"] == "KC-807-MD"


def test_unrecognised_plate_is_only_trimmed_and_uppercased(conn):
    claim = clean_one(conn, vehicle_registrations="Other vehicle:  x9 y  ")
    assert claim["other_vehicle"] == "X9 Y"


@pytest.mark.parametrize("text, expected", [
    ("Claimant vehicle: AB15 CDE; Other vehicle: XY21 ZZZ", ("AB15 CDE", "XY21 ZZZ")),
    ("Claimant vehicle: AB15 CDE", ("AB15 CDE", None)),
    ("Other vehicle: XY21 ZZZ", (None, "XY21 ZZZ")),
    ("", (None, None)),
    (None, (None, None)),
    ("  Claimant vehicle:   AB15 CDE  ;   Other vehicle:   XY21 ZZZ ", ("AB15 CDE", "XY21 ZZZ")),
    ("Claimant vehicle: ; Other vehicle: XY21 ZZZ", (None, "XY21 ZZZ")),
])
def test_registrations_are_split_into_two_plates(text, expected):
    assert split_registrations(text) == expected


def test_missing_registrations_leave_both_plates_null(conn):
    claim = clean_one(conn, vehicle_registrations="")
    assert claim["claimant_vehicle"] is None and claim["other_vehicle"] is None


@pytest.mark.parametrize("name, expected", [
    ("Kate Owen", ("Kate", "Owen")),
    ("Mary Ann Smith", ("Mary", "Smith")),
    ("Cher", ("Cher", None)),
    ("  Kate   Owen ", ("Kate", "Owen")),
    ("", (None, None)),
    (None, (None, None)),
])
def test_names_are_split_into_first_name_and_surname(name, expected):
    assert split_name(name) == expected


def test_cleaning_stores_the_name_parts(conn):
    claim = clean_one(conn, claimant_name=" Kate Owen ")
    assert (claim["first_name"], claim["surname"]) == ("Kate", "Owen")


def test_dates_are_stored_as_iso(conn):
    claim = clean_one(conn, received_date="05/10/25", accident_date="3rd August",
                      date_of_birth="20/07/70")
    assert (claim["received_date"], claim["accident_date"], claim["date_of_birth"]) == \
        ("2025-10-05", "2025-08-03", "1970-07-20")


def test_cleaning_twice_changes_nothing(conn):
    first = clean_rows(conn, make_raw_claim(postcode="ch14bq"))
    snapshot = dict(first["FN-00001"])
    cleaning.clean_claims(conn)
    assert dict(conn.execute("SELECT * FROM claims").fetchone()) == snapshot
