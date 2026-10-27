"""Parse scripture references the way operators actually type (or hear) them.

Handles "Jer 29:11", "john 3 16", "jn3.16", "1 cor 13:4-7", "psalm 23",
"rom 8 28 to 30", "gen 1:1-2:3", "John chapter 3 verse 16" and spoken numbers
such as "first corinthians thirteen four" or "psalm one hundred and nineteen".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import books

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9,
}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def words_to_digits(text: str) -> str:
    """Replace runs of English number words with digits ("twenty three" -> "23")."""
    tokens = re.findall(r"[a-z]+|\d+|[^a-z\d\s]|\s+", text.lower())
    out: list[str] = []
    cur: int | None = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            out.append(str(cur))
            cur = None

    words = tokens
    i = 0
    while i < len(words):
        tok = words[i]
        nxt = next((w for w in words[i + 1 :] if not w.isspace()), "")
        if tok.isspace():
            if cur is None:
                out.append(tok)
            i += 1
            continue
        if tok == "-" and cur is not None and cur >= 20 and cur % 10 == 0 and nxt in _UNITS:
            i += 1  # "twenty-three"
            continue
        if tok in _UNITS:
            if cur is not None and (cur % 10 != 0 or 10 <= cur % 100 < 20):
                flush()
                out.append(" ")
            cur = (cur or 0) + _UNITS[tok]
        elif tok in _TEENS:
            if cur is not None and cur % 100 != 0:
                flush()
                out.append(" ")
            cur = (cur or 0) + _TEENS[tok]
        elif tok in _TENS:
            if cur is not None and cur % 100 != 0:
                flush()
                out.append(" ")
            cur = (cur or 0) + _TENS[tok]
        elif tok == "hundred":
            cur = (cur or 1) * 100
        elif tok == "a" and nxt == "hundred" and cur is None:
            cur = 0  # "a hundred" -> 100 once "hundred" multiplies (0 or 1)
        elif tok == "and" and cur is not None and cur >= 100 and cur % 100 == 0 and (
            nxt in _UNITS or nxt in _TEENS or nxt in _TENS
        ):
            pass
        else:
            if cur is not None:
                flush()
                out.append(" ")
            out.append(tok)
        i += 1
    flush()
    return re.sub(r"\s+", " ", "".join(out)).strip()


@dataclass(frozen=True)
class Reference:
    book: int
    chapter: int
    verse: int | None = None  # None = whole chapter
    end_chapter: int | None = None
    end_verse: int | None = None

    @property
    def is_range(self) -> bool:
        return self.end_verse is not None and (
            self.end_verse != self.verse or (self.end_chapter or self.chapter) != self.chapter
        )

    @property
    def book_name(self) -> str:
        return books.NAMES[self.book]

    def display(self) -> str:
        s = f"{self.book_name} {self.chapter}"
        if self.verse is None:
            return s
        s += f":{self.verse}"
        if self.is_range:
            if self.end_chapter and self.end_chapter != self.chapter:
                s += f"-{self.end_chapter}:{self.end_verse}"
            else:
                s += f"-{self.end_verse}"
        return s

    def first_verse(self) -> "Reference":
        return Reference(self.book, self.chapter, self.verse or 1)


_FILLER = re.compile(r"\b(chapter|chap|ch|verses|verse|vv|vs|v)\b\.?")
_RANGE_WORDS = re.compile(r"\s*(?:\bto\b|\bthrough\b|\bthru\b|\btill\b|\buntil\b|–|—|-)\s*")

_REF_RE = re.compile(
    r"""^\s*
    (?P<book>(?:[123]\s*)?[a-z][a-z ]*?)\s*
    (?P<ch>\d{1,3})
    (?:\s*[:.\s]\s*(?P<v>\d{1,3}))?
    (?:\s*-\s*(?P<a>\d{1,3})(?:\s*[:.]\s*(?P<b>\d{1,3}))?)?
    \s*$""",
    re.VERBOSE,
)


def _normalize(query: str) -> str:
    q = query.lower().strip()
    q = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", q)  # "1st john" -> "1 john"
    q = words_to_digits(q) if re.search(r"[a-z]", q) else q
    q = q.replace(",", " ")
    q = _FILLER.sub(" ", q)
    q = _RANGE_WORDS.sub("-", q)
    q = re.sub(r"(?<=[a-z])(?=\d)", " ", q)  # "jn3.16" -> "jn 3.16"
    # "1 john" style books where the digit got split from the name keep working.
    return re.sub(r"\s+", " ", q).strip()


def parse(query: str) -> Reference | None:
    """Return a Reference if the whole query is a scripture reference, else None."""
    if not query or not re.search(r"\d", query) and not re.search(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
        r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\b",
        query.lower(),
    ):
        return None
    q = _normalize(query)
    m = _REF_RE.match(q)
    if not m:
        return None
    book = books.find_book(m.group("book"))
    if book is None:
        return None
    ch = int(m.group("ch"))
    v = int(m.group("v")) if m.group("v") else None
    a = int(m.group("a")) if m.group("a") else None
    b = int(m.group("b")) if m.group("b") else None
    if ch == 0 or v == 0:
        return None
    if v is None:
        if a is not None and b is None:
            # "psalm 23-24" is a chapter range; keep the first chapter.
            return Reference(book, ch)
        if a is not None and b is not None:
            return Reference(book, ch, 1, a, b)
        return Reference(book, ch)
    if a is None:
        return Reference(book, ch, v, ch, v)
    if b is not None:
        return Reference(book, ch, v, a, b)
    if a < v:
        return Reference(book, ch, v, ch, v)
    return Reference(book, ch, v, ch, a)
