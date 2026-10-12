"""Step 1b: clean the loaded claims (SQL, with Python only for dates, names and plate splitting)."""
import re
from datetime import date

ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
SLASH_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
ORDINAL_RE = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)$", re.IGNORECASE)

MONTHS = {
    name: number for number, name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"], start=1)
}


def _make_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _age_on(born, on_date):
    return on_date.year - born.year - ((on_date.month, on_date.day) < (born.month, born.day))


def _date_without_year(day, month_name, received):
    """3rd April: take the received year; if that is after the received date, the year before."""
    month = MONTHS.get(month_name.lower())
    if month is None or received is None:
        return None
    found = _make_date(received.year, month, day)
    if found and found > received:
        found = _make_date(received.year - 1, month, day)
    return found


def _parse_date_object(text, received, two_digit_year):
    """Shared reader for the three accepted formats; two_digit_year(yy, month, day) picks the century."""
    text = (text or "").strip()
    if match := ISO_RE.match(text):
        year, month, day = map(int, match.groups())
        return _make_date(year, month, day)
    if match := SLASH_RE.match(text):
        day, month, yy = map(int, match.groups())
        return two_digit_year(yy, month, day)
    if match := ORDINAL_RE.match(text):
        return _date_without_year(int(match.group(1)), match.group(2), received)
    return None


def _iso(found):
    return found.isoformat() if found else None


def _as_date(iso_text):
    return date.fromisoformat(iso_text) if iso_text else None


def parse_date(text, received=None):
    """Received or accident date to ISO text; two-digit years become 20YY. None if unreadable."""
    received_date = _as_date(received)
    return _iso(_parse_date_object(
        text, received_date, lambda yy, month, day: _make_date(2000 + yy, month, day)))


def parse_birth_date(text, accident):
    """Date of birth to ISO text; a two-digit year is 19YY if the age on the accident date is 100 or less."""
    accident_date = _as_date(accident)

    def century(yy, month, day):
        if accident_date is None:
            return None
        born = _make_date(1900 + yy, month, day)
        if born and _age_on(born, accident_date) <= 100:
            return born
        return _make_date(2000 + yy, month, day)

    return _iso(_parse_date_object(text, None, century))


# ---------------------------------------------------------------------------
# Names and registrations (Python: SQL can't split these sensibly)
# ---------------------------------------------------------------------------

CLAIMANT_PLATE_RE = re.compile(r"Claimant vehicle:\s*([^;]*)", re.IGNORECASE)
OTHER_PLATE_RE = re.compile(r"Other vehicle:\s*([^;]*)", re.IGNORECASE)


def split_name(full_name):
    """First word and last word of a name; (None, None) if blank, no surname for one word."""
    words = (full_name or "").split()
    if not words:
        return None, None
    return words[0], (words[-1] if len(words) > 1 else None)


def _plate_after_label(pattern, registrations):
    match = pattern.search(registrations or "")
    return (match.group(1).strip() or None) if match else None


def split_registrations(registrations):
    """'Claimant vehicle: X; Other vehicle: Y' -> (X, Y); either may be None."""
    return (_plate_after_label(CLAIMANT_PLATE_RE, registrations),
            _plate_after_label(OTHER_PLATE_RE, registrations))


# ---------------------------------------------------------------------------
# The cleaning run
# ---------------------------------------------------------------------------

TEXT_COLUMNS = [
    "claimant_name", "postcode", "phone", "email", "accident_location",
    "road_user_type", "other_driver_insurer", "accident_description",
    "injuries_described", "time_off_work",
]
WHITESPACE = "' ' || char(9) || char(10) || char(13)"
UK_PLATE_GLOB = "[A-Z][A-Z][0-9][0-9][A-Z][A-Z][A-Z]"

REQUIRED_TEXT = ["claimant_name", "accident_description"]
REQUIRED_DATES = ["received_date", "accident_date"]


def trim_text_fields(conn):
    """SQL: copy the text fields from raw_claims with spaces trimmed; blank becomes NULL."""
    assignments = ", ".join(
        f"{c} = NULLIF(TRIM(r.{c}, {WHITESPACE}), '')" for c in TEXT_COLUMNS)
    conn.execute(
        f"UPDATE claims SET {assignments} FROM raw_claims r "
        "WHERE r.reference = claims.reference AND claims.status = 'loaded'")


def clean_dates_names_and_plates(conn):
    """Python, row by row: dates to ISO, name parts, and the two plates split out."""
    rows = conn.execute(
        "SELECT r.reference, r.received_date, r.accident_date, r.date_of_birth, "
        "r.vehicle_registrations, c.claimant_name FROM claims c "
        "JOIN raw_claims r USING (reference) WHERE c.status = 'loaded'").fetchall()
    for row in rows:
        received = parse_date(row["received_date"])
        accident = parse_date(row["accident_date"], received)
        birth = parse_birth_date(row["date_of_birth"], accident)
        note = None
        if row["date_of_birth"].strip() and birth is None:
            note = "Date of birth could not be read"
        first, surname = split_name(row["claimant_name"])
        claimant_plate, other_plate = split_registrations(row["vehicle_registrations"])
        conn.execute(
            "UPDATE claims SET received_date = ?, accident_date = ?, date_of_birth = ?, "
            "cleaning_note = ?, first_name = ?, surname = ?, claimant_vehicle = ?, "
            "other_vehicle = ? WHERE reference = ?",
            (received, accident, birth, note, first, surname,
             claimant_plate, other_plate, row["reference"]))


def format_postcodes(conn):
    """SQL: uppercase with a single space before the last three characters."""
    squashed = "upper(replace(postcode, ' ', ''))"
    conn.execute(
        f"UPDATE claims SET postcode = CASE WHEN length({squashed}) >= 5 "
        f"THEN substr({squashed}, 1, length({squashed}) - 3) || ' ' || substr({squashed}, -3) "
        f"ELSE {squashed} END WHERE status = 'loaded' AND postcode IS NOT NULL")


def format_plates(conn):
    """SQL: UK plates become AB15 CDE; anything else (e.g. AB-123-CD) is only uppercased."""
    for column in ("claimant_vehicle", "other_vehicle"):
        squashed = f"upper(replace({column}, ' ', ''))"
        conn.execute(
            f"UPDATE claims SET {column} = CASE WHEN {squashed} GLOB '{UK_PLATE_GLOB}' "
            f"THEN substr({squashed}, 1, 4) || ' ' || substr({squashed}, 5) "
            f"ELSE upper({column}) END WHERE status = 'loaded' AND {column} IS NOT NULL")


def _required_field_problems():
    """SQL text that joins every missing or unreadable required field into one reason."""
    parts = ["CASE WHEN w.reference = '' THEN 'Missing required field: reference; ' END"]
    parts += [f"CASE WHEN c.{f} IS NULL THEN 'Missing required field: {f}; ' END"
              for f in REQUIRED_TEXT]
    parts += [
        f"CASE WHEN TRIM(w.{f}, {WHITESPACE}) = '' THEN 'Missing required field: {f}; ' "
        f"WHEN c.{f} IS NULL THEN 'Unreadable required date: {f}; ' END"
        for f in REQUIRED_DATES]
    return " || ".join(f"COALESCE({p}, '')" for p in parts)


def set_aside_incomplete_rows(conn):
    """SQL: a missing or unreadable required field means status rejected, with a reason."""
    conn.execute(
        "UPDATE claims SET status = 'rejected', reject_reason = rtrim(x.problems, '; ') "
        f"FROM (SELECT c.reference AS ref, {_required_field_problems()} AS problems "
        "FROM claims c JOIN raw_claims w USING (reference) WHERE c.status = 'loaded') x "
        "WHERE claims.reference = x.ref AND x.problems <> ''")
    conn.execute("UPDATE claims SET status = 'cleaned' WHERE status = 'loaded'")


def flag_impossible_dates(conn):
    """SQL: record why a date is impossible; step 2 turns this into the route."""
    problems = (
        "COALESCE(CASE WHEN accident_date > received_date "
        "THEN 'Accident date is after the date received; ' END, '') || "
        "COALESCE(CASE WHEN date_of_birth > accident_date "
        "THEN 'Date of birth is after the accident date; ' END, '')")
    conn.execute(
        f"UPDATE claims SET date_problem = NULLIF(rtrim({problems}, '; '), '') "
        "WHERE status = 'cleaned'")


def clean_claims(conn):
    trim_text_fields(conn)
    clean_dates_names_and_plates(conn)
    format_postcodes(conn)
    format_plates(conn)
    set_aside_incomplete_rows(conn)
    flag_impossible_dates(conn)
    conn.commit()
