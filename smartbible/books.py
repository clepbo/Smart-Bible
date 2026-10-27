"""Canonical list of the 66 books, with the names and abbreviations people type."""

from __future__ import annotations

import re

# (number, display name, short abbreviation, extra aliases)
_BOOKS: list[tuple[int, str, str, tuple[str, ...]]] = [
    (1, "Genesis", "Gen", ("ge", "gn")),
    (2, "Exodus", "Exod", ("ex", "exo")),
    (3, "Leviticus", "Lev", ("le", "lv")),
    (4, "Numbers", "Num", ("nu", "nm", "nb")),
    (5, "Deuteronomy", "Deut", ("dt", "deu", "de")),
    (6, "Joshua", "Josh", ("jos", "jsh")),
    (7, "Judges", "Judg", ("jdg", "jg", "jdgs")),
    (8, "Ruth", "Ruth", ("rth", "ru")),
    (9, "1 Samuel", "1Sam", ("1sa", "1sm", "1s")),
    (10, "2 Samuel", "2Sam", ("2sa", "2sm", "2s")),
    (11, "1 Kings", "1Kgs", ("1ki", "1kg", "1k", "1kin")),
    (12, "2 Kings", "2Kgs", ("2ki", "2kg", "2k", "2kin")),
    (13, "1 Chronicles", "1Chr", ("1ch", "1chron", "1chr")),
    (14, "2 Chronicles", "2Chr", ("2ch", "2chron", "2chr")),
    (15, "Ezra", "Ezra", ("ezr",)),
    (16, "Nehemiah", "Neh", ("ne",)),
    (17, "Esther", "Esth", ("est", "es")),
    (18, "Job", "Job", ("jb",)),
    (19, "Psalms", "Ps", ("psalm", "psa", "psm", "pss", "pslm")),
    (20, "Proverbs", "Prov", ("pr", "prv", "pro", "proverb")),
    (21, "Ecclesiastes", "Eccl", ("ec", "ecc", "eccles", "qoh", "qohelet")),
    (22, "Song of Solomon", "Song", ("so", "sos", "song of songs", "songs", "canticles", "sng")),
    (23, "Isaiah", "Isa", ("is",)),
    (24, "Jeremiah", "Jer", ("je", "jr")),
    (25, "Lamentations", "Lam", ("la",)),
    (26, "Ezekiel", "Ezek", ("eze", "ezk")),
    (27, "Daniel", "Dan", ("da", "dn")),
    (28, "Hosea", "Hos", ("ho",)),
    (29, "Joel", "Joel", ("jl", "joe")),
    (30, "Amos", "Amos", ("am",)),
    (31, "Obadiah", "Obad", ("ob", "oba")),
    (32, "Jonah", "Jonah", ("jon", "jnh")),
    (33, "Micah", "Mic", ("mi", "mc")),
    (34, "Nahum", "Nah", ("na",)),
    (35, "Habakkuk", "Hab", ("hb",)),
    (36, "Zephaniah", "Zeph", ("zep", "zp")),
    (37, "Haggai", "Hag", ("hg",)),
    (38, "Zechariah", "Zech", ("zec", "zc")),
    (39, "Malachi", "Mal", ("ml",)),
    (40, "Matthew", "Matt", ("mt", "mat")),
    (41, "Mark", "Mark", ("mk", "mrk", "mr", "mar")),
    (42, "Luke", "Luke", ("lk", "luk", "lu")),
    (43, "John", "John", ("jn", "jhn", "joh")),
    (44, "Acts", "Acts", ("ac", "act", "acts of the apostles")),
    (45, "Romans", "Rom", ("ro", "rm")),
    (46, "1 Corinthians", "1Cor", ("1co",)),
    (47, "2 Corinthians", "2Cor", ("2co",)),
    (48, "Galatians", "Gal", ("ga",)),
    (49, "Ephesians", "Eph", ("ephes", "ep")),
    (50, "Philippians", "Phil", ("php", "pp", "philip")),
    (51, "Colossians", "Col", ("co",)),
    (52, "1 Thessalonians", "1Thess", ("1th", "1thes", "1ts")),
    (53, "2 Thessalonians", "2Thess", ("2th", "2thes", "2ts")),
    (54, "1 Timothy", "1Tim", ("1ti", "1tm")),
    (55, "2 Timothy", "2Tim", ("2ti", "2tm")),
    (56, "Titus", "Titus", ("tit", "ti")),
    (57, "Philemon", "Phlm", ("phm", "philem", "phile")),
    (58, "Hebrews", "Heb", ("he",)),
    (59, "James", "Jas", ("jm", "jam", "jms")),
    (60, "1 Peter", "1Pet", ("1pe", "1pt", "1p")),
    (61, "2 Peter", "2Pet", ("2pe", "2pt", "2p")),
    (62, "1 John", "1John", ("1jn", "1jo", "1jhn", "1j")),
    (63, "2 John", "2John", ("2jn", "2jo", "2jhn", "2j")),
    (64, "3 John", "3John", ("3jn", "3jo", "3jhn", "3j")),
    (65, "Jude", "Jude", ("jud", "jd")),
    (66, "Revelation", "Rev", ("re", "rv", "revelations", "revelation of john", "apocalypse")),
]

NAMES: dict[int, str] = {n: name for n, name, _, _ in _BOOKS}
ABBREVIATIONS: dict[int, str] = {n: abbr for n, _, abbr, _ in _BOOKS}

_ORDINAL_WORDS = {
    "1": ("1", "i", "first", "1st", "one"),
    "2": ("2", "ii", "second", "2nd", "two"),
    "3": ("3", "iii", "third", "3rd", "three"),
}


def normalize_book_key(text: str) -> str:
    """Lower-case, drop dots, and turn "First John"/"I John"/"1st John" into "1john"."""
    s = text.lower().replace(".", " ").strip()
    s = re.sub(r"\s+", " ", s)
    parts = s.split(" ", 1)
    if len(parts) == 2:
        for digit, words in _ORDINAL_WORDS.items():
            if parts[0] in words:
                s = digit + parts[1]
                break
    return s.replace(" ", "")


def _build_lookup() -> dict[str, int]:
    lookup: dict[str, int] = {}
    for n, name, abbr, aliases in _BOOKS:
        for key in (name, abbr, *aliases):
            lookup[normalize_book_key(key)] = n
    # Allow "Song of Songs" style keys with and without "of"
    lookup.setdefault("songofsongs", 22)
    return lookup


_LOOKUP = _build_lookup()
# Keys sorted longest first so prefix matching prefers "1john" over "1jo".
_KEYS_BY_LENGTH = sorted(_LOOKUP, key=len, reverse=True)


def find_book(text: str) -> int | None:
    """Return the book number for a typed book name, or None.

    Accepts full names, standard abbreviations and unambiguous prefixes
    ("jerem", "philipp").
    """
    key = normalize_book_key(text)
    if not key:
        return None
    if key in _LOOKUP:
        return _LOOKUP[key]
    if len(key) >= 3:
        matches = {n for k, n in _LOOKUP.items() if k.startswith(key)}
        if len(matches) == 1:
            return matches.pop()
    return None


def book_name_pattern() -> str:
    """Regex alternation matching every known book key at the start of a query."""
    return "|".join(re.escape(k) for k in _KEYS_BY_LENGTH)
