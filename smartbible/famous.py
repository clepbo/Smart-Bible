"""Well-known passages and the nicknames preachers use for them."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import reference
from .bible import verse_key
from .keyword import tokenize


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("'", "")))


@dataclass
class FamousPassage:
    ref: reference.Reference
    names: list[str]
    tokens: list[set[str]]


class FamousIndex:
    def __init__(self, path: Path):
        self.passages: list[FamousPassage] = []
        for entry in json.loads(path.read_text(encoding="utf-8")):
            ref = reference.parse(entry["ref"])
            if ref is None:
                raise ValueError(f"famous.json: cannot parse {entry['ref']!r}")
            names = entry["names"]
            self.passages.append(FamousPassage(ref, names, [set(tokenize(n)) for n in names]))
        self.popular_keys: set[int] = set()
        for p in self.passages:
            r = p.ref
            if r.verse is None:
                continue
            end = r.end_verse if (r.end_chapter or r.chapter) == r.chapter and r.end_verse else r.verse
            for v in range(r.verse, (end or r.verse) + 1):
                self.popular_keys.add(verse_key(r.book, r.chapter, v))

    def match(self, query: str, limit: int = 3) -> list[tuple[reference.Reference, float, str]]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        q_set = set(q_tokens)
        partial = q_tokens[-1] if not query.endswith(" ") and len(q_tokens[-1]) >= 3 else None
        q_text = " ".join(query.lower().split())
        found: list[tuple[reference.Reference, float, str]] = []
        for p in self.passages:
            best = 0.0
            best_name = ""
            for name, n_set in zip(p.names, p.tokens):
                if not n_set:
                    continue
                overlap = len(q_set & n_set)
                if partial and partial not in n_set and any(t.startswith(partial) for t in n_set):
                    overlap += 1
                need = min(2, len(n_set))
                score = 0.0
                if overlap >= need:
                    covers_query = overlap / len(q_set)
                    covers_name = overlap / len(n_set)
                    if covers_query >= 0.75:
                        # Same words in any order: good, but below an in-order match.
                        score = 0.85 * covers_query * (0.4 + 0.6 * covers_name)
                q_plain = _plain(q_text)
                if len(q_plain) >= 6 and q_plain in _plain(name):
                    score = max(score, 0.9 + 0.1 * len(q_plain) / len(_plain(name)))
                if len(q_text) >= 6:
                    short = name[4:] if name.startswith("the ") else name
                    q_short = q_text[4:] if q_text.startswith("the ") else q_text
                    ratio = difflib.SequenceMatcher(None, q_short, short).ratio()
                    if ratio >= 0.82:  # typos like "prodical son"
                        score = max(score, ratio)
                if score > best:
                    best, best_name = score, name
            if best >= 0.55:
                found.append((p.ref, best, best_name))
        found.sort(key=lambda x: -x[1])
        return found[:limit]
