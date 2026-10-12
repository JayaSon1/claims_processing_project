import pytest

from dedupe import surnames_close


@pytest.mark.parametrize("x, y", [
    ("Owen", "Owen"),
    ("Owen", "OWEN"),
    ("owen", "Owen"),
])
def test_identical_surnames_match_whatever_the_case(x, y):
    assert surnames_close(x, y)


@pytest.mark.parametrize("full, short", [
    ("Hughes", "ughes"),      # first letter missing
    ("Hughes", "Hughs"),      # middle letter missing
    ("Hughes", "Hughe"),      # last letter missing
    ("Patel", "Patl"),
])
def test_one_missing_letter_matches_in_either_direction(full, short):
    assert surnames_close(full, short)
    assert surnames_close(short, full)


@pytest.mark.parametrize("x, y", [
    ("Hughes", "Huhges"),
    ("Owen", "Owne"),
    ("Owen", "Woen"),
    ("Khan", "Kahn"),
])
def test_two_neighbouring_letters_swapped_match(x, y):
    assert surnames_close(x, y)


@pytest.mark.parametrize("x, y", [
    ("Smith", "Smyth"),        # one letter substituted
    ("Hughes", "Hugh"),        # two letters missing
    ("Owen", "Ewon"),          # two letters swapped, but not neighbours
    ("Owen", "Nwoe"),          # several letters differ
    ("Patel", "Morgan"),       # completely different
    ("Patel", "Patels2"),      # two letters added
    ("Patel", "Pxtels"),       # one letter added and one changed
])
def test_other_differences_do_not_match(x, y):
    assert not surnames_close(x, y)


@pytest.mark.parametrize("x, y", [(None, "Owen"), ("Owen", None), (None, None), ("", "Owen"), ("", "")])
def test_empty_or_missing_surnames_never_match(x, y):
    assert not surnames_close(x, y)
