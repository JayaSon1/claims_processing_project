"""Step 1c: find duplicate claims and link them to the claim kept."""


def _one_letter_missing(shorter, longer):
    return len(longer) - len(shorter) == 1 and any(
        longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))


def _neighbouring_letters_swapped(x, y):
    if len(x) != len(y):
        return False
    differing = [i for i, (p, q) in enumerate(zip(x, y)) if p != q]
    if len(differing) != 2 or differing[1] != differing[0] + 1:
        return False
    first, second = differing
    return x[first] == y[second] and x[second] == y[first]


def surnames_close(x, y):
    """True if surnames are identical or differ by one letter missing or two neighbours swapped."""
    if not x or not y:
        return False
    x, y = x.lower(), y.lower()
    return (x == y
            or _one_letter_missing(x, y) or _one_letter_missing(y, x)
            or _neighbouring_letters_swapped(x, y))


# Claims "a" and "b" look like the same person: matching name (first name and close surname) or same email.
SAME_NAME_OR_EMAIL = (
    "((lower(a.first_name) = lower(b.first_name) AND surnames_close(a.surname, b.surname)) "
    "OR lower(a.email) = lower(b.email))")

FIND_PAIRS_SQL = f"""
SELECT a.reference AS kept, b.reference AS later
FROM claims a JOIN claims b
  ON a.date_of_birth = b.date_of_birth AND a.accident_date = b.accident_date
WHERE a.status = 'cleaned' AND b.status = 'cleaned'
  AND (a.received_date, a.reference) < (b.received_date, b.reference)
  AND {SAME_NAME_OR_EMAIL}
ORDER BY b.received_date, b.reference, a.received_date, a.reference
"""

REVIEW_NOTE_SQL = f"""
UPDATE claims AS a SET duplicate_review_note = 'Possible duplicate of ' || (
    SELECT b.reference FROM claims b
    WHERE b.status = 'cleaned' AND b.reference <> a.reference
      AND b.accident_date = a.accident_date AND {SAME_NAME_OR_EMAIL}
    ORDER BY b.reference LIMIT 1
) || '. Date of birth is missing, so the duplicate check could not be run. Please check.'
WHERE a.status = 'cleaned' AND a.date_of_birth IS NULL AND EXISTS (
    SELECT 1 FROM claims b
    WHERE b.status = 'cleaned' AND b.reference <> a.reference
      AND b.accident_date = a.accident_date AND {SAME_NAME_OR_EMAIL})
"""


def _root_claim(conn, reference):
    """The claim that is actually kept: follows duplicate links to the end."""
    while True:
        row = conn.execute(
            "SELECT status, duplicate_of FROM claims WHERE reference = ?", (reference,)).fetchone()
        if row["status"] != "duplicate":
            return reference
        reference = row["duplicate_of"]


def _mark_duplicate(conn, later, kept):
    conn.execute(
        "UPDATE claims SET status = 'duplicate', duplicate_of = ? "
        "WHERE reference = ? AND status = 'cleaned'", (kept, later))


def merge_duplicates(conn):
    for pair in conn.execute(FIND_PAIRS_SQL).fetchall():
        if conn.execute("SELECT status FROM claims WHERE reference = ?",
                        (pair["later"],)).fetchone()["status"] == "cleaned":
            _mark_duplicate(conn, pair["later"], _root_claim(conn, pair["kept"]))


def flag_possible_duplicates_without_birth_date(conn):
    conn.execute(REVIEW_NOTE_SQL)


def find_duplicates(conn):
    conn.create_function("surnames_close", 2, surnames_close, deterministic=True)
    merge_duplicates(conn)
    flag_possible_duplicates_without_birth_date(conn)
    conn.commit()
