"""Download public-domain English translations and store them in data/bibles.

Source: https://github.com/scrollmapper/bible_databases (formats/json).
Only public-domain texts are fetched; copyrighted translations (NIV, NKJV,
ESV, AMP, ...) must be supplied by the church from a licensed copy.

    python scripts/fetch_bibles.py
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartbible.bible import clean_text  # noqa: E402

BASE = "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/formats/json/"

TRANSLATIONS = {
    "KJV": "King James Version",
    "BSB": "Berean Standard Bible",
    "NHEB": "New Heart English Bible",
    "ASV": "American Standard Version",
    "BBE": "Bible in Basic English",
    "YLT": "Young's Literal Translation",
}


def convert(bible_id: str, name: str, data: dict) -> dict:
    books = data["books"]
    if len(books) != 66:
        raise ValueError(f"{bible_id}: expected 66 books, got {len(books)}")
    verses = []
    for b, book in enumerate(books, start=1):
        for chapter in book["chapters"]:
            for verse in chapter["verses"]:
                text = clean_text(verse["text"])
                if text:
                    verses.append([b, chapter["chapter"], verse["verse"], text])
    return {"id": bible_id, "name": name, "license": "Public domain", "verses": verses}


def main() -> None:
    out_dir = ROOT / "data" / "bibles"
    out_dir.mkdir(parents=True, exist_ok=True)
    for bible_id, name in TRANSLATIONS.items():
        print(f"Fetching {bible_id}...")
        with urllib.request.urlopen(BASE + f"{bible_id}.json", timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8-sig"))
        converted = convert(bible_id, name, data)
        payload = json.dumps(converted, ensure_ascii=False, separators=(",", ":")).encode()
        (out_dir / f"{bible_id}.json.gz").write_bytes(gzip.compress(payload, 9))
        print(f"  {len(converted['verses'])} verses")


if __name__ == "__main__":
    main()
