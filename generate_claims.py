# Claim Generation Script
# Generates a reproducible batch of 150 SYNTHETIC road-traffic personal-injury claim notifications 

# Steps
# 1. Builds 144 "base" claims and 6 duplicate re-submissions (150 rows in total)
# 2. Deliberately makes roughly 30% of rows messy, in exactly the ways set out in the project plan:
# - duplicates (same claim twice, with a name typo or a different email)
# - dates in mixed formats (03/04/25, 3rd April, 2025-04-03)
# - accident dates that fall after the received date
# - missing fields (date of birth, other-party insurer, registration)
# - inconsistent postcodes and number plates (case, spacing)
# - facts that appear only in the free text ("I was on my bike", "my 15-year-old son was in the back", "the other car had French plates")
# - contradictions (form says "driver", text says "I was crossing the road")
# 3. Makes sure the batch contains enough claims of every kind needed to pick the 12 pilot cases by hand (straightforward OIC-eligible, children,
#    cyclists/pedestrians, foreign-registered defendant vehicle, close to the 3-year limitation date, duplicate, contradiction)
# 4. Runs validation checks on the written CSV and stops with an error if any check fails


# Synthetic-data safeguards
# - Phone numbers use the Ofcom range reserved for drama (07700 900000-900999)
# - Email addresses use domains reserved for examples (example.com/.net/.org)
# - Insurer names are fictional
# - Names, postcodes and number plates are randomly combined. They follow real UK formats, so a combination may coincidentally match a real person, place or vehicle


# Reproducibility
# Everything random comes from one `random.Random(SEED)` instance, and today's date is fixed - running the script again always produces a byte-identical file
# The validation step checks this by generating the batch twice and comparing hashes

import csv
import hashlib
import io
import random
import re
from datetime import date, timedelta


# Configuration
SEED = 20261009   # change this and you get a different (but still reproducible) batch
OUTPUT_FILE = "claim_notifications.csv"

N_ROWS = 150                         # total rows in the CSV
N_DUPLICATES = 6                     # duplicate re-submissions (each copies one base claim)
N_BASE = N_ROWS - N_DUPLICATES       # 144 original claims

# Fixed "today" so the output does not depend on when the script is run
TODAY = date(2026, 10, 9)

# Claims are received over the last 12 months or so
RECEIVED_START = date(2025, 10, 1)
RECEIVED_END = date(2026, 10, 8)

# OIC rule: road-traffic accident on or after 31 May 2021
# Every real accident date generated here is after this, and validation checks it
OIC_START = date(2021, 5, 31)

# Column order
FIELDS = [
    "reference",
    "received_date",
    "claimant_name",
    "date_of_birth",
    "postcode",
    "phone",
    "email",
    "accident_date",
    "accident_location",
    "road_user_type",
    "vehicle_registrations",
    "other_driver_insurer",
    "accident_description",
    "injuries_described",
    "time_off_work",
]

# Clean (not messy) claims that sit on non-OIC routes. These are stated
# clearly in the form, so they are not counted as "mess"; they exist so
# that every pilot route has candidates to choose from.
N_CYCLIST = 6
N_PEDESTRIAN = 5
N_MOTORCYCLIST = 3
N_CHILD = 5               # child claimant, date of birth given
N_FOREIGN = 3             # defendant vehicle registered abroad, stated in the form
N_NEAR_LIMITATION = 4     # accident between ~2 years 9 months and 3 years before received date

# Mess applied to ordinary base claims. Each count is applied to a different
# row, so the number of affected rows is the sum of these plus the duplicates:
# 41 + 6 = 47 of 150 rows (31%).
MESS_PLAN = {
    "text_only_bike": 3,          # road-user type blank; text says "I was on my bike"
    "text_only_child": 3,         # child's date of birth blank; age only in text
    "text_only_foreign": 3,       # foreign plates only mentioned in text
    "contradiction": 4,           # form says driver; text says crossing the road
    "missing_dob": 3,
    "missing_insurer": 3,
    "missing_registration": 2,
    "mixed_date_format": 9,       # one or more dates as 03/04/25 or 3rd April
    "accident_after_received": 3,
    "messy_postcode_plate": 8,    # wrong case or spacing in postcode and/or plate
}

# Target band for the share of affected rows ("roughly 30%").
MESS_SHARE_MIN, MESS_SHARE_MAX = 0.25, 0.35

# How many candidates of each pilot route must exist in the batch.
PILOT_NEEDS = {
    "straightforward": 4,
    "child": 2,
    "vulnerable_road_user": 2,
    "foreign_vehicle": 1,
    "near_limitation": 1,
    "duplicate": 1,
    "contradiction": 1,
}

# ---------------------------------------------------------------------------
# Word lists (all synthetic)
# ---------------------------------------------------------------------------

ADULT_FIRST = [
    "James", "Sarah", "Mohammed", "Emma", "Daniel", "Aisha", "Thomas", "Chloe",
    "Ryan", "Hannah", "Liam", "Priya", "Connor", "Megan", "Adam", "Sophie",
    "Kieran", "Jessica", "Owen", "Laura", "Bilal", "Rachel", "Jack", "Amy",
    "Gareth", "Natalie", "Imran", "Rebecca", "Callum", "Zara", "Lewis", "Kate",
]
CHILD_FIRST = {
    "son": ["Oliver", "Harry", "Noah", "Leo", "Alfie", "Yusuf", "Jacob", "Theo"],
    "daughter": ["Isla", "Ava", "Mia", "Freya", "Amelia", "Maryam", "Poppy", "Grace"],
}
SURNAMES = [
    "Hughes", "Patel", "Roberts", "Khan", "Davies", "Jones", "Williams", "Evans",
    "Thompson", "Ali", "Wright", "Walker", "Edwards", "Hussain", "Morris", "Price",
    "Griffiths", "Shah", "Kelly", "Turner", "Parry", "Begum", "Lloyd", "Morgan",
    "Harrison", "Ahmed", "Clarke", "Jenkins", "Owen", "Bennett",
]

# Real-format outward codes (area + district); the inward part is random.
POSTCODE_OUTWARD = [
    "CH1", "CH2", "CH3", "CH4", "CH65", "L8", "L15", "L36", "M14", "M20",
    "WA1", "WA5", "LL11", "SK4", "CW1", "CH41", "B23", "LS6", "S10", "NG7",
]
# Letters allowed in the last two characters of a UK postcode (excludes C, I, K, M, O, V).
POSTCODE_INWARD_LETTERS = "ABDEFGHJLNPQRSTUWXYZ"

# Letters used in random plate sections (I and Q are not used on UK plates).
PLATE_LETTERS = "ABCDEFGHJKLMNOPRSTUVWXY"
PLATE_AGE_IDS = ["15", "65", "16", "66", "18", "68", "19", "69", "21", "71", "22", "72", "24", "74"]

ROADS = [
    "Station Road", "Hoole Road", "Liverpool Road", "Grosvenor Road", "Parkgate Road",
    "High Street", "Church Lane", "Victoria Road", "London Road", "Mill Lane",
    "Chester Road", "Wrexham Road", "Manchester Road", "Queens Road",
]
TOWNS = [
    "Chester", "Wrexham", "Warrington", "Liverpool", "Manchester",
    "Crewe", "Ellesmere Port", "Birkenhead",
]

UK_INSURERS = [
    "Northgate Motor Insurance", "Severn Mutual", "Pennine Direct", "Harbour Line Insurance",
    "Kestrel Motor Cover", "Redwood General", "Castlegate Insurance", "Meridian Drive Insurance",
]
FOREIGN_INSURERS = ["Assurances Lumière (France)", "Assurances Côte Ouest (France)"]

EMAIL_DOMAINS = ["example.com", "example.net", "example.org"]

# ---------------------------------------------------------------------------
# Free-text building blocks
# Each string is exactly ONE sentence, so sentence counts stay predictable.
# {road} is filled with a road name; {rel} with "son" or "daughter";
# {age} with the child's age.
# ---------------------------------------------------------------------------

OPENINGS = {
    "driver": [
        "I was stopped at the traffic lights on {road} when a car went into the back of me.",
        "I was driving along {road} and a car pulled out of a side road straight into my passenger side.",
        "I was waiting to turn right off {road} when the car behind didn't stop in time and hit me.",
        "I was sat in a queue of traffic on {road} and got shunted from behind.",
    ],
    "passenger": [
        "I was in the front passenger seat of my partner's car on {road} when we were hit from behind.",
        "I was a passenger in my friend's car on {road} and another car drove into the side of us at a roundabout.",
        "I was sitting in the back of a taxi on {road} when a van ran into the back of it.",
    ],
    "cyclist": [
        "I was cycling along {road} when a car turned left across me and knocked me off.",
        "I was cycling in the bike lane on {road} and a driver opened their door right in front of me.",
    ],
    "pedestrian": [
        "I was crossing {road} at the zebra crossing when a car didn't stop and hit me.",
        "I was walking across {road} at the lights when a car came through on red and clipped me.",
    ],
    "motorcyclist": [
        "I was riding my motorbike along {road} when a van changed lanes into me.",
        "I was on my motorbike waiting at a junction on {road} when a car hit me from behind.",
    ],
    "child": [
        "My {rel} was in the back of my car on {road} when another car drove into the back of us.",
        "My {rel} was sitting in the back seat when we were hit at the roundabout on {road}.",
    ],
    # Mess scenarios: the key fact is ONLY in this sentence, not in the form.
    "text_only_bike": [
        "I was on my bike going along {road} when a car pulled out of a junction and hit me.",
        "I was on my bike at the lights on {road} when a car turned into me.",
    ],
    "text_only_child": [
        "We were stopped in traffic on {road} and my {age}-year-old {rel} was in the back when a car went into us.",
    ],
    # Contradiction: the form will say "driver", but this sentence says pedestrian.
    "contradiction": [
        "I was crossing the road on {road} when a car came round the corner too fast and hit me.",
        "I was crossing the road near the shops on {road} when a car reversed out and knocked me over.",
    ],
}

EXTRAS = {
    # For drivers and passengers.
    "vehicle": [
        "The other driver said sorry and gave me their insurance details.",
        "We swapped details at the side of the road but the police didn't come.",
        "My neck started to hurt that evening and was worse the next morning.",
        "I went to see my GP about a week later because the pain wasn't going away.",
        "The car had to be taken away on a recovery truck.",
        "I've been struggling to sleep properly since it happened.",
        "It was raining and quite dark at the time.",
    ],
    # For cyclists, pedestrians, motorcyclists (and the mess scenarios that
    # are really one of these).
    "vulnerable": [
        "The driver stopped and gave me their details.",
        "A passer-by helped me up and called an ambulance.",
        "I went to A&E that night and they said nothing was broken.",
        "I've been really nervous going near roads since.",
        "My back and shoulder have been painful ever since.",
    ],
    # For claims made on behalf of a child, written by the parent.
    "child": [
        "We went to the walk-in centre the next day to get them checked over.",
        "The other driver admitted it was their fault.",
        "They have been complaining of a sore neck since.",
        "They were very shaken up afterwards.",
    ],
}

# The sentence that is the only place the foreign registration appears.
FOREIGN_TEXT_ONLY_SENTENCE = (
    "The other car had French plates and the driver didn't have any insurance papers with them."
)

INJURIES = {
    "vehicle": [
        "Neck pain and stiffness",
        "Neck and shoulder pain",
        "Lower back pain",
        "Whiplash, neck pain and headaches",
        "Bruising across my chest from the seatbelt and a sore neck",
        "Pain in my neck and upper back",
        "Sore neck and a stiff left shoulder",
    ],
    "vulnerable": [
        "Grazes on both arms and a sprained wrist",
        "Bruised hip and knee, sore back",
        "Cut to my hand and pain in my shoulder",
        "Sprained ankle and bruising down my left side",
    ],
    "child": [
        "Sore neck",
        "Neck pain and a headache",
        "Bruising from the seatbelt",
    ],
}

TIME_OFF = {
    "adult": [
        "None", "1 day", "3 days", "1 week", "2 weeks",
        "Still off work", "Not working at the moment", "Half a day for the GP appointment",
    ],
    "child": ["N/A - at school", "Missed 2 days of school", "None"],
}

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def random_date(rng, start, end):
    """Uniform random date between start and end (inclusive)."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


def age_on(dob, on_date):
    """Whole years of age on a given date."""
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def add_years(d, years):
    """Same day N years later (29 Feb falls back to 28 Feb)."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def make_dob(rng, accident, min_age, max_age):
    """Date of birth giving an age between min_age and max_age at the accident."""
    while True:
        dob = accident - timedelta(days=rng.randint(min_age * 365, (max_age + 1) * 365))
        if min_age <= age_on(dob, accident) <= max_age:
            return dob


def make_postcode(rng):
    """A correctly formatted UK postcode, e.g. 'CH1 4BQ'."""
    return (
        f"{rng.choice(POSTCODE_OUTWARD)} "
        f"{rng.randint(1, 9)}{rng.choice(POSTCODE_INWARD_LETTERS)}{rng.choice(POSTCODE_INWARD_LETTERS)}"
    )


def make_uk_plate(rng):
    """A correctly formatted current-style UK plate, e.g. 'AB15 CDE'."""
    area = rng.choice(PLATE_LETTERS) + rng.choice(PLATE_LETTERS)
    tail = "".join(rng.choice(PLATE_LETTERS) for _ in range(3))
    return f"{area}{rng.choice(PLATE_AGE_IDS)} {tail}"


def make_french_plate(rng):
    """A French-style plate, e.g. 'GH-482-TK'."""
    letters = lambda: rng.choice(PLATE_LETTERS) + rng.choice(PLATE_LETTERS)
    return f"{letters()}-{rng.randint(100, 999)}-{letters()}"


def make_phone(rng):
    """Phone number in the Ofcom drama range (never allocated to real people)."""
    return f"07700 900{rng.randint(0, 999):03d}"


def make_email(rng, first, last):
    """Email address on a reserved example domain."""
    return f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@{rng.choice(EMAIL_DOMAINS)}"


def make_location(rng, road):
    """Accident location: a road, or a junction, plus a town."""
    town = rng.choice(TOWNS)
    if rng.random() < 0.4:
        other = rng.choice([r for r in ROADS if r != road])
        return f"Junction of {road} and {other}, {town}"
    return f"{road}, {town}"


def ordinal(n):
    """1 -> '1st', 2 -> '2nd', 11 -> '11th', 23 -> '23rd'."""
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def fmt_iso(d):
    """Canonical format used by clean rows: 2025-04-03."""
    return d.isoformat()


def fmt_slash(d):
    """Messy format: 03/04/25 (day/month/two-digit year)."""
    return d.strftime("%d/%m/%y")


def fmt_ordinal(d):
    """Messy format: 3rd April (no year, as a claimant might write it)."""
    return f"{ordinal(d.day)} {d.strftime('%B')}"


def mess_postcode(rng, pc):
    """Wrong case and/or spacing, e.g. 'ch1 4bq', 'CH14BQ', 'ch1  4bq'."""
    return rng.choice([pc.lower(), pc.replace(" ", ""), pc.lower().replace(" ", "  ")])


def mess_plate(rng, plate):
    """Wrong case and/or spacing, e.g. 'ab15 cde', 'AB15CDE', 'AB 15 CDE'."""
    return rng.choice([
        plate.lower(),
        plate.replace(" ", ""),
        f"{plate[:2]} {plate[2:]}",
    ])


def typo(rng, word):
    """Introduce a one-character typo: swap two adjacent letters or drop one."""
    while True:
        i = rng.randint(1, len(word) - 2)
        if rng.random() < 0.5:
            new = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        else:
            new = word[:i] + word[i + 1:]
        if new != word:
            return new


def build_description(rng, opening_key, extras_key, n_extra, special=None, **fmt):
    """
    Assemble the free-text description from one opening sentence, n_extra
    supporting sentences and (optionally) one special sentence that carries
    a fact found only in the text. Result is 2 to 6 sentences.
    """
    sentences = [rng.choice(OPENINGS[opening_key]).format(**fmt)]
    sentences += rng.sample(EXTRAS[extras_key], n_extra)
    if special:
        sentences.insert(rng.randint(1, len(sentences)), special)
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def new_claim(rng, scenario):
    """
    Create one base claim as an internal record. Dates are kept as `date`
    objects here and only turned into text when the CSV is written, so the
    mess can be applied in one place.

    `scenario` controls the kind of claimant and how the form is filled in.
    """
    road = rng.choice(ROADS)
    received = random_date(rng, RECEIVED_START, RECEIVED_END)

    # Most accidents are reported within four months.
    if scenario == "near_limitation":
        # Between about 2 years 9 months (1005 days) and 3 years minus 10 days.
        received = random_date(rng, date(2026, 6, 1), RECEIVED_END)
        accident = received - timedelta(days=rng.randint(1005, 1085))
    else:
        accident = received - timedelta(days=rng.randint(2, 120))

    # Who the claimant is and what the form says.
    is_child = scenario in ("child", "text_only_child")
    rel = rng.choice(["son", "daughter"]) if is_child else None
    first = rng.choice(CHILD_FIRST[rel]) if is_child else rng.choice(ADULT_FIRST)
    last = rng.choice(SURNAMES)
    dob = make_dob(rng, accident, 9, 16) if is_child else make_dob(rng, accident, 18, 79)

    if scenario in ("cyclist", "pedestrian", "motorcyclist"):
        road_user = scenario
    elif is_child:
        road_user = "passenger"
    elif scenario == "text_only_bike":
        road_user = ""                       # left blank on the form
    elif scenario == "contradiction":
        road_user = "driver"                 # the text will contradict this
    else:
        road_user = "driver" if rng.random() < 0.7 else "passenger"

    # Vehicles involved: only drivers (and the contradiction, whose form says
    # driver) list their own vehicle.
    own_plate = make_uk_plate(rng) if road_user == "driver" else None
    if scenario == "foreign":
        other_plate, insurer = make_french_plate(rng), rng.choice(FOREIGN_INSURERS)
    elif scenario == "text_only_foreign":
        other_plate, insurer = None, ""      # foreign plates only in the text
    else:
        other_plate, insurer = make_uk_plate(rng), rng.choice(UK_INSURERS)

    # Free-text description, injuries and time off.
    n_extra = rng.randint(1, 4)              # opening + 1-4 extras = 2-5 sentences
    if scenario in ("cyclist", "pedestrian", "motorcyclist"):
        desc = build_description(rng, scenario, "vulnerable", n_extra, road=road)
        injuries = rng.choice(INJURIES["vulnerable"])
    elif scenario == "text_only_bike":
        desc = build_description(rng, "text_only_bike", "vulnerable", n_extra, road=road)
        injuries = rng.choice(INJURIES["vulnerable"])
    elif scenario == "contradiction":
        desc = build_description(rng, "contradiction", "vulnerable", n_extra, road=road)
        injuries = rng.choice(INJURIES["vulnerable"])
    elif scenario == "child":
        desc = build_description(rng, "child", "child", n_extra, road=road, rel=rel)
        injuries = rng.choice(INJURIES["child"])
    elif scenario == "text_only_child":
        desc = build_description(
            rng, "text_only_child", "child", n_extra,
            road=road, rel=rel, age=age_on(dob, accident),
        )
        injuries = rng.choice(INJURIES["child"])
    else:
        special = FOREIGN_TEXT_ONLY_SENTENCE if scenario == "text_only_foreign" else None
        desc = build_description(rng, road_user, "vehicle", n_extra, special=special, road=road)
        injuries = rng.choice(INJURIES["vehicle"])

    return {
        "received": received,
        "first": first,
        "last": last,
        "dob": dob,
        "show_dob": scenario != "text_only_child",   # child's age only in the text
        "postcode": make_postcode(rng),
        "phone": make_phone(rng),
        "email": make_email(rng, first, last),
        "accident": accident,
        "location": make_location(rng, road),
        "road_user": road_user,
        "own_plate": own_plate,
        "other_plate": other_plate,
        "foreign_plate": scenario == "foreign",
        "insurer": insurer,
        "description": desc,
        "injuries": injuries,
        "time_off": rng.choice(TIME_OFF["child" if is_child else "adult"]),
        # Formatting choices; changed below for messy rows.
        "date_formats": {"received": fmt_iso, "dob": fmt_iso, "accident": fmt_iso},
        "show_registrations": True,
        "mess_postcode": False,
        "mess_plates": False,
        # Internal metadata, used only for validation; never written to the CSV.
        "meta": {"scenario": scenario, "mess": []},
    }


def apply_mess(rng, rec, kind):
    """Apply one mess type to an ordinary base claim (mutates the record)."""
    if kind == "missing_dob":
        rec["show_dob"] = False
    elif kind == "missing_insurer":
        rec["insurer"] = ""
    elif kind == "missing_registration":
        rec["show_registrations"] = False
    elif kind == "accident_after_received":
        # A typo-style error: the accident date is days or weeks after receipt.
        rec["accident"] = rec["received"] + timedelta(days=rng.randint(3, 30))
    elif kind == "mixed_date_format":
        # Reformat one or two of the three dates; the accident date may be
        # written without a year ("3rd April"), the others as 03/04/25.
        fields = rng.sample(["received", "dob", "accident"], rng.randint(1, 2))
        for f in fields:
            if f == "accident" and rng.random() < 0.6:
                rec["date_formats"][f] = fmt_ordinal
            else:
                rec["date_formats"][f] = fmt_slash
    elif kind == "messy_postcode_plate":
        mode = rng.choice(["postcode", "plate", "both"])
        rec["mess_postcode"] = mode in ("postcode", "both")
        rec["mess_plates"] = mode in ("plate", "both")
    rec["meta"]["mess"].append(kind)


def make_duplicate(rng, original):
    """
    Copy a claim as if it had been submitted twice: received the same day or
    up to two days later, with either a typo in the surname or a different
    email address. Everything else is identical.
    """
    dup = {k: (dict(v) if isinstance(v, dict) else v) for k, v in original.items()}
    dup["meta"] = {"scenario": original["meta"]["scenario"], "mess": ["duplicate"]}
    dup["date_formats"] = dict(original["date_formats"])
    dup["received"] = original["received"] + timedelta(days=rng.randint(0, 2))
    if rng.random() < 0.5:
        dup["last"] = typo(rng, original["last"])
    else:
        dup["email"] = make_email(rng, original["first"], original["last"])
        while dup["email"] == original["email"]:
            dup["email"] = make_email(rng, original["first"], original["last"])
    original["meta"]["has_duplicate"] = True
    return dup


def to_row(rng, rec):
    """Turn an internal record into a CSV row (all text)."""
    fmt = rec["date_formats"]

    own, other = rec["own_plate"], rec["other_plate"]
    if rec["mess_plates"]:
        own = mess_plate(rng, own) if own else own
        other = mess_plate(rng, other) if other else other
    parts = []
    if own:
        parts.append(f"Claimant vehicle: {own}")
    if other:
        parts.append(f"Other vehicle: {other}")
    registrations = "; ".join(parts) if rec["show_registrations"] else ""

    postcode = mess_postcode(rng, rec["postcode"]) if rec["mess_postcode"] else rec["postcode"]

    return {
        "reference": "",                    # filled in after sorting
        "received_date": fmt["received"](rec["received"]),
        "claimant_name": f"{rec['first']} {rec['last']}",
        "date_of_birth": fmt["dob"](rec["dob"]) if rec["show_dob"] else "",
        "postcode": postcode,
        "phone": rec["phone"],
        "email": rec["email"],
        "accident_date": fmt["accident"](rec["accident"]),
        "accident_location": rec["location"],
        "road_user_type": rec["road_user"],
        "vehicle_registrations": registrations,
        "other_driver_insurer": rec["insurer"],
        "accident_description": rec["description"],
        "injuries_described": rec["injuries"],
        "time_off_work": rec["time_off"],
    }


def generate(seed):
    """
    Build the full batch. Returns (rows, records): rows are what goes in the
    CSV; records hold the internal metadata used only by validation.
    """
    rng = random.Random(seed)

    # 1. Decide the scenario for each of the 144 base claims.
    scenarios = (
        ["cyclist"] * N_CYCLIST
        + ["pedestrian"] * N_PEDESTRIAN
        + ["motorcyclist"] * N_MOTORCYCLIST
        + ["child"] * N_CHILD
        + ["foreign"] * N_FOREIGN
        + ["near_limitation"] * N_NEAR_LIMITATION
        + ["text_only_bike"] * MESS_PLAN["text_only_bike"]
        + ["text_only_child"] * MESS_PLAN["text_only_child"]
        + ["text_only_foreign"] * MESS_PLAN["text_only_foreign"]
        + ["contradiction"] * MESS_PLAN["contradiction"]
    )
    scenarios += ["ordinary"] * (N_BASE - len(scenarios))
    records = [new_claim(rng, s) for s in scenarios]

    # The four scenario-based mess types are already built in; record them.
    for rec in records:
        if rec["meta"]["scenario"] in ("text_only_bike", "text_only_child",
                                      "text_only_foreign", "contradiction"):
            rec["meta"]["mess"].append(rec["meta"]["scenario"])

    # 2. Apply the remaining mess types, each to a different ordinary claim.
    ordinary = [r for r in records if r["meta"]["scenario"] == "ordinary"]
    rng.shuffle(ordinary)
    pool = iter(ordinary)
    for kind in ("missing_dob", "missing_insurer", "missing_registration",
                 "mixed_date_format", "accident_after_received", "messy_postcode_plate"):
        for _ in range(MESS_PLAN[kind]):
            apply_mess(rng, next(pool), kind)

    # 3. Duplicates: copy untouched ordinary claims (the next ones in the pool).
    duplicates = [make_duplicate(rng, next(pool)) for _ in range(N_DUPLICATES)]
    records += duplicates

    # 4. Sort by received date (then by name, for a stable order) and assign
    #    references in that order, as a case system would.
    records.sort(key=lambda r: (r["received"], r["last"], r["first"]))
    rows = []
    for i, rec in enumerate(records, start=1):
        row = to_row(rng, rec)
        row["reference"] = f"FN-{i:05d}"
        rows.append(row)
    return rows, records


def rows_to_csv_text(rows):
    """Serialise rows to CSV text (used for writing and for the hash check)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLASH_RE = re.compile(r"^\d{2}/\d{2}/\d{2}$")
ORDINAL_RE = re.compile(r"^\d{1,2}(st|nd|rd|th) [A-Z][a-z]+$")
POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]? \d[A-Z]{2}$")
UK_PLATE_RE = re.compile(r"^[A-Z]{2}\d{2} [A-Z]{3}$")
FR_PLATE_RE = re.compile(r"^[A-Z]{2}-\d{3}-[A-Z]{2}$")
PHONE_RE = re.compile(r"^07700 900\d{3}$")
REF_RE = re.compile(r"^FN-\d{5}$")
CHILD_TEXT_RE = re.compile(r"my \d{1,2}-year-old (son|daughter)")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Fields that must never be blank. (Date of birth, road-user type,
# registrations and insurer may be blank, but only as deliberate mess.)
ALWAYS_PRESENT = [
    "reference", "received_date", "claimant_name", "postcode", "phone", "email",
    "accident_date", "accident_location", "accident_description",
    "injuries_described", "time_off_work",
]


def plates_in(field):
    """Pull the plate strings out of the vehicle_registrations field."""
    return [p.split(": ", 1)[1] for p in field.split("; ") if ": " in p]


def validate(path, records):
    """
    Check the written CSV against the specification. Every failed check is
    collected and reported together; any failure stops the script.
    """
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    # --- Structure ---------------------------------------------------------
    check(header == FIELDS, f"Header does not match the field list: {header}")
    check(len(rows) == N_ROWS, f"Expected {N_ROWS} rows, found {len(rows)}")

    refs = [r["reference"] for r in rows]
    check(len(set(refs)) == len(refs), "References are not unique")
    check(all(REF_RE.match(x) for x in refs), "A reference is not in FN-00000 format")

    for r in rows:
        for field in ALWAYS_PRESENT:
            check(r[field].strip() != "", f"{r['reference']}: '{field}' is blank")

    # --- Free text: 2 to 6 sentences ----------------------------------------
    for r in rows:
        n = len(SENTENCE_SPLIT.split(r["accident_description"].strip()))
        check(2 <= n <= 6, f"{r['reference']}: description has {n} sentences (need 2-6)")

    # --- Synthetic-data safeguards ------------------------------------------
    check(all(PHONE_RE.match(r["phone"]) for r in rows), "A phone number is outside the 07700 900xxx drama range")
    check(all(r["email"].split("@")[-1] in EMAIL_DOMAINS for r in rows), "An email is not on a reserved example domain")

    # --- Roughly 30% of rows affected by mess -------------------------------
    affected = sum(1 for rec in records if rec["meta"]["mess"])
    share = affected / len(records)
    check(MESS_SHARE_MIN <= share <= MESS_SHARE_MAX,
          f"Messy share is {share:.0%}; expected {MESS_SHARE_MIN:.0%}-{MESS_SHARE_MAX:.0%}")

    # --- Each mess type is visible in the CSV itself ------------------------
    date_cols = ["received_date", "date_of_birth", "accident_date"]
    all_dates = [r[c] for r in rows for c in date_cols if r[c]]
    check(any(SLASH_RE.match(d) for d in all_dates), "No dates in 03/04/25 format")
    check(any(ORDINAL_RE.match(r["accident_date"]) for r in rows), "No accident dates in '3rd April' format")
    check(sum(bool(ISO_RE.match(d)) for d in all_dates) > len(all_dates) / 2,
          "ISO (2025-04-03) should be the majority date format")
    for d in all_dates:
        check(ISO_RE.match(d) or SLASH_RE.match(d) or ORDINAL_RE.match(d),
              f"Unexpected date format: {d!r}")

    after = [r for r in rows
             if ISO_RE.match(r["accident_date"]) and ISO_RE.match(r["received_date"])
             and r["accident_date"] > r["received_date"]]
    check(len(after) >= 1, "No accident dates after the received date")

    check(any(r["date_of_birth"] == "" for r in rows), "No rows with a missing date of birth")
    check(any(r["other_driver_insurer"] == "" for r in rows), "No rows with a missing insurer")
    check(any(r["vehicle_registrations"] == "" for r in rows), "No rows with a missing registration")

    check(any(not POSTCODE_RE.match(r["postcode"]) for r in rows), "No inconsistent postcodes")
    all_plates = [p for r in rows for p in plates_in(r["vehicle_registrations"])]
    check(any(not (UK_PLATE_RE.match(p) or FR_PLATE_RE.match(p)) for p in all_plates),
          "No inconsistent number plates")

    texts = [r["accident_description"] for r in rows]
    check(any("on my bike" in t for t in texts), "No 'on my bike' fact in the free text")
    check(any(CHILD_TEXT_RE.search(t) for t in texts), "No 'my N-year-old son/daughter' fact in the free text")
    check(any("French plates" in t for t in texts), "No 'French plates' fact in the free text")
    check(any(r["road_user_type"] == "driver" and "crossing the road" in r["accident_description"]
              for r in rows), "No driver/crossing-the-road contradiction")

    # Duplicates: rows sharing accident date, location and description.
    groups = {}
    for r in rows:
        key = (r["accident_date"], r["accident_location"], r["accident_description"])
        groups.setdefault(key, []).append(r)
    pairs = [g for g in groups.values() if len(g) == 2]
    check(len(pairs) == N_DUPLICATES, f"Expected {N_DUPLICATES} duplicate pairs, found {len(pairs)}")
    check(all(len(g) <= 2 for g in groups.values()), "A claim appears more than twice")
    for a, b in pairs:
        check(a["claimant_name"] != b["claimant_name"] or a["email"] != b["email"],
              f"Duplicate pair {a['reference']}/{b['reference']} has no name typo or email change")

    # --- OIC date rule and limitation window (internal true dates) -----------
    for rec in records:
        check(rec["accident"] >= OIC_START, "An accident date is before 31 May 2021")
        if rec["meta"]["scenario"] == "near_limitation":
            check(add_years(rec["accident"], 3) > rec["received"] >= rec["accident"] + timedelta(days=1005),
                  "A near-limitation claim is outside the 2y9m-3y window")
        elif "accident_after_received" not in rec["meta"]["mess"]:
            check((rec["received"] - rec["accident"]).days <= 120,
                  "An ordinary claim was reported more than 4 months after the accident")

    # --- Enough candidates for every pilot route -----------------------------
    clean = [rec for rec in records if not rec["meta"]["mess"]]
    available = {
        "straightforward": sum(1 for rec in clean
                               if rec["meta"]["scenario"] == "ordinary"
                               and not rec["meta"].get("has_duplicate")),
        "child": sum(1 for rec in records if rec["meta"]["scenario"] in ("child", "text_only_child")
                     and "duplicate" not in rec["meta"]["mess"]),
        "vulnerable_road_user": sum(1 for rec in records
                                    if rec["meta"]["scenario"] in ("cyclist", "pedestrian")),
        "foreign_vehicle": sum(1 for rec in records
                               if rec["meta"]["scenario"] in ("foreign", "text_only_foreign")),
        "near_limitation": sum(1 for rec in records if rec["meta"]["scenario"] == "near_limitation"),
        "duplicate": sum(1 for rec in records if "duplicate" in rec["meta"]["mess"]),
        "contradiction": sum(1 for rec in records if rec["meta"]["scenario"] == "contradiction"),
    }
    for route, need in PILOT_NEEDS.items():
        check(available[route] >= need,
              f"Only {available[route]} candidates for pilot route '{route}' (need {need})")

    # --- Children really are under 18; adults really are 18+ -----------------
    for rec in records:
        age = age_on(rec["dob"], rec["accident"])
        if rec["meta"]["scenario"] in ("child", "text_only_child"):
            check(age < 18, "A child claimant is 18 or over")
        else:
            check(age >= 18, "An adult claimant is under 18")

    return errors, affected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    rows, records = generate(SEED)
    text = rows_to_csv_text(rows)

    # Reproducibility: the same seed must give a byte-identical file.
    rows_again, _ = generate(SEED)
    same = hashlib.sha256(text.encode()).hexdigest() == \
        hashlib.sha256(rows_to_csv_text(rows_again).encode()).hexdigest()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        f.write(text)

    errors, affected = validate(OUTPUT_FILE, records)
    if not same:
        errors.append("Generating twice with the same seed gave different output")

    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    # Totals only, never per-row categories, so labelling stays independent.
    print(f"Wrote {len(rows)} rows to {OUTPUT_FILE} (seed {SEED})")
    print(f"Rows affected by mess: {affected} of {len(rows)} ({affected / len(rows):.0%})")
    print("All validation checks passed; output is reproducible.")


if __name__ == "__main__":
    main()
