"""Loading Bible translations from disk.

Bundled translations live in ``data/bibles/<ID>.json.gz`` with the shape::

    {"id": "KJV", "name": "King James Version", "verses": [[book, chapter, verse, text], ...]}

Users can add their own (licensed) translations by dropping a file into the
user bible folder. Supported formats: our JSON (optionally gzipped), CSV
(``book,chapter,verse,text``) and Zefania XML.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import books


def verse_key(book: int, chapter: int, verse: int) -> int:
    return book * 1_000_000 + chapter * 1_000 + verse


def split_key(key: int) -> tuple[int, int, int]:
    return key // 1_000_000, (key // 1_000) % 1_000, key % 1_000


@dataclass
class Bible:
    id: str
    name: str
    texts: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._finalize()

    def _finalize(self) -> None:
        self.keys = sorted(self.texts)
        self._last_verse: dict[tuple[int, int], int] = {}
        self._last_chapter: dict[int, int] = {}
        for key in self.keys:
            b, c, v = split_key(key)
            if v > self._last_verse.get((b, c), 0):
                self._last_verse[(b, c)] = v
            if c > self._last_chapter.get(b, 0):
                self._last_chapter[b] = c

    def text(self, book: int, chapter: int, verse: int) -> str | None:
        return self.texts.get(verse_key(book, chapter, verse))

    def last_verse(self, book: int, chapter: int) -> int:
        return self._last_verse.get((book, chapter), 0)

    def last_chapter(self, book: int) -> int:
        return self._last_chapter.get(book, 0)

    def has(self, book: int, chapter: int, verse: int) -> bool:
        return verse_key(book, chapter, verse) in self.texts


# ---------------------------------------------------------------- loading


def _from_rows(bible_id: str, name: str, rows) -> Bible:
    texts: dict[int, str] = {}
    for b, c, v, t in rows:
        t = clean_text(str(t))
        if t:
            texts[verse_key(int(b), int(c), int(v))] = t
    return Bible(bible_id, name, texts)


def clean_text(text: str) -> str:
    text = text.replace("`", "'").replace("¶", "")
    text = re.sub(r"<[^>]+>", "", text)  # stray markup
    return re.sub(r"\s+", " ", text).strip()


def _book_number(value: str) -> int:
    value = value.strip()
    if value.isdigit():
        return int(value)
    n = books.find_book(value)
    if n is None:
        raise ValueError(f"Unknown book name: {value!r}")
    return n


def load_json(path: Path) -> Bible:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8-sig"))
    stem = path.name.split(".")[0]
    if "verses" in data:
        return _from_rows(data.get("id", stem), data.get("name", stem), data["verses"])
    if "books" in data:  # scrollmapper-style nested JSON
        rows = []
        for i, book in enumerate(data["books"], start=1):
            for chapter in book["chapters"]:
                for verse in chapter["verses"]:
                    rows.append((i, chapter["chapter"], verse["verse"], verse["text"]))
        name = data.get("translation", stem).split(":", 1)[-1].strip()
        return _from_rows(stem, name, rows)
    raise ValueError(f"{path.name}: unrecognised JSON layout")


def load_csv(path: Path) -> Bible:
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for row in reader:
        if len(row) < 4:
            continue
        if not row[1].strip().isdigit():  # header line
            continue
        rows.append((_book_number(row[0]), row[1], row[2], ",".join(row[3:])))
    return _from_rows(path.stem, path.stem, rows)


def load_zefania(path: Path) -> Bible:
    root = ET.parse(path).getroot()
    name = root.get("biblename") or path.stem
    title = root.find("./INFORMATION/title")
    if title is not None and title.text:
        name = title.text.strip()
    rows = []
    for book in root.iter("BIBLEBOOK"):
        b = int(book.get("bnumber"))
        for chapter in book.iter("CHAPTER"):
            c = int(chapter.get("cnumber"))
            for vers in chapter.iter("VERS"):
                rows.append((b, c, int(vers.get("vnumber")), "".join(vers.itertext())))
    return _from_rows(path.stem, name, rows)


def load_file(path: Path) -> Bible:
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".json") or suffixes.endswith(".json.gz"):
        return load_json(path)
    if suffixes.endswith(".csv"):
        return load_csv(path)
    if suffixes.endswith(".xml"):
        return load_zefania(path)
    raise ValueError(f"Unsupported Bible file: {path.name}")


class Library:
    """All translations available to the app, keyed by ID."""

    def __init__(self, folders: list[Path]):
        self.bibles: dict[str, Bible] = {}
        self.errors: list[str] = []
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if not path.is_file():
                    continue
                try:
                    bible = load_file(path)
                except ValueError as exc:
                    if "Unsupported" not in str(exc):
                        self.errors.append(str(exc))
                    continue
                except Exception as exc:  # malformed user file must not crash the app
                    self.errors.append(f"{path.name}: {exc}")
                    continue
                self.bibles[bible.id] = bible

    def ids(self) -> list[str]:
        return list(self.bibles)

    def get(self, bible_id: str) -> Bible | None:
        return self.bibles.get(bible_id)

    def any(self) -> Bible:
        return next(iter(self.bibles.values()))
