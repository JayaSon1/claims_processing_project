"""Step 1a: load the claim notifications CSV into raw_claims and claims."""
import csv

from db import CSV_COLUMNS


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"The CSV is missing expected columns: {', '.join(missing)}")
        return list(reader)


def insert_rows(conn, rows):
    """Add rows not already present; return how many were new."""
    columns = ", ".join(CSV_COLUMNS)
    marks = ", ".join("?" for _ in CSV_COLUMNS)
    added = 0
    for row in rows:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO raw_claims ({columns}) VALUES ({marks})",
            [row[c] for c in CSV_COLUMNS],
        )
        if cur.rowcount:
            conn.execute("INSERT INTO claims (reference) VALUES (?)", (row["reference"],))
            added += 1
    conn.commit()
    return added


def load_claims(conn, path):
    return insert_rows(conn, read_csv_rows(path))
