"""Database connection and tables for the claims pilot."""
import os
import sqlite3

DB_PATH = os.environ.get("DATABASE_PATH", "claims.db")

CSV_COLUMNS = [
    "reference", "received_date", "claimant_name", "date_of_birth", "postcode",
    "phone", "email", "accident_date", "accident_location", "road_user_type",
    "vehicle_registrations", "other_driver_insurer", "accident_description",
    "injuries_described", "time_off_work",
]

CLAIM_STATES = (
    "loaded", "cleaned", "extracted", "awaiting_check1", "drafted",
    "awaiting_check2", "approved", "rejected", "duplicate", "on_hold",
)

RAW_COLUMNS_SQL = ",\n    ".join(
    f"{c} TEXT NOT NULL" if c != "reference" else "reference TEXT PRIMARY KEY"
    for c in CSV_COLUMNS
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS raw_claims (
    {RAW_COLUMNS_SQL}
);

CREATE TABLE IF NOT EXISTS claims (
    reference TEXT PRIMARY KEY REFERENCES raw_claims(reference),
    status TEXT NOT NULL DEFAULT 'loaded'
        CHECK (status IN ({", ".join(repr(s) for s in CLAIM_STATES)})),
    reject_reason TEXT,
    duplicate_of TEXT REFERENCES claims(reference),
    date_problem TEXT,
    cleaning_note TEXT,
    duplicate_review_note TEXT,
    received_date TEXT,
    accident_date TEXT,
    date_of_birth TEXT,
    claimant_name TEXT,
    first_name TEXT,
    surname TEXT,
    postcode TEXT,
    phone TEXT,
    email TEXT,
    accident_location TEXT,
    road_user_type TEXT,
    claimant_vehicle TEXT,
    other_vehicle TEXT,
    other_driver_insurer TEXT,
    accident_description TEXT,
    injuries_described TEXT,
    time_off_work TEXT
);
"""


def create_tables(conn):
    conn.executescript(SCHEMA)


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn
