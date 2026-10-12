"""Build step 1: load, clean and de-duplicate the claim notifications.

Run: python prepare_claims.py
"""
import db
from cleaning import clean_claims
from dedupe import find_duplicates
from loading import load_claims

CSV_PATH = "claim_notifications.csv"


def prepare_claims(conn, csv_path=CSV_PATH):
    """Run the three parts of step 1 in order; return how many rows were newly loaded."""
    added = load_claims(conn, csv_path)
    clean_claims(conn)
    find_duplicates(conn)
    return added


def count_where(conn, condition):
    return conn.execute(f"SELECT COUNT(*) FROM claims WHERE {condition}").fetchone()[0]


def print_totals(conn, added):
    print(f"Newly loaded: {added}")
    print(f"Claims in database: {count_where(conn, '1 = 1')}")
    print(f"Rejected (set aside): {count_where(conn, 'status = ' + repr('rejected'))}")
    print(f"Duplicates merged: {count_where(conn, 'status = ' + repr('duplicate'))}")
    print(f"Cleaned and kept: {count_where(conn, 'status = ' + repr('cleaned'))}")
    print(f"Impossible dates flagged: {count_where(conn, 'date_problem IS NOT NULL')}")
    print(f"Possible duplicates to check (no date of birth): "
          f"{count_where(conn, 'duplicate_review_note IS NOT NULL')}")


if __name__ == "__main__":
    connection = db.connect()
    print_totals(connection, prepare_claims(connection))
