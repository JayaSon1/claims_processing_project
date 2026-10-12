import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import loading  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def conn():
    connection = db.connect(":memory:")
    yield connection
    connection.close()


def make_raw_claim(**overrides):
    """One valid raw claim row (all text); override any field."""
    row = {
        "reference": "FN-00001", "received_date": "2025-10-05",
        "claimant_name": "Kate Owen", "date_of_birth": "1970-07-20",
        "postcode": "CH2 9EA", "phone": "07700 900724",
        "email": "kate.owen71@example.org", "accident_date": "2025-08-15",
        "accident_location": "London Road, Warrington",
        "road_user_type": "driver",
        "vehicle_registrations": "Claimant vehicle: AB15 CDE; Other vehicle: SL72 VVP",
        "other_driver_insurer": "Meridian Drive Insurance",
        "accident_description": "I was stopped at the lights when a car hit me.",
        "injuries_described": "Neck pain", "time_off_work": "None",
    }
    row.update(overrides)
    return row


def add_claims(conn, *rows):
    """Load raw rows into the database as the loader would."""
    loading.insert_rows(conn, list(rows))


def clean_rows(conn, *rows):
    """Load raw rows, run cleaning, and return the claims keyed by reference."""
    import cleaning
    add_claims(conn, *rows)
    cleaning.clean_claims(conn)
    return {r["reference"]: r for r in conn.execute("SELECT * FROM claims")}


def clean_one(conn, **overrides):
    return clean_rows(conn, make_raw_claim(**overrides))["FN-00001"]
