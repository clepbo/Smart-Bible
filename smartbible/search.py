"""The search engine: combines every offline signal into one ranked list."""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from . import reference
from .bible import Bible, Library, split_key, verse_key
from .famous import FamousIndex
from .keyword import KeywordIndex
from .semantic import SemanticIndex

SOURCE_LABELS = {
    "reference": "Reference",
    "famous": "Well-known passage",
    "ai": "AI",
    "keyword": "Words",
    "meaning": "Meaning",
    "phrase": "Exact phrase",
}


@dataclass
class Result:
    ref: reference.Reference
    score: float
    sources: set[str] = field(default_factory=set)
    note: str = ""

    @property
    def key(self) -> tuple:
        r = self.ref
        return (r.book, r.chapter, r.verse, r.end_chapter, r.end_verse)


def _plain(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("’", "'").replace("'", "")))


class SearchEngine:
    def __init__(self, library: Library, famous: FamousIndex, semantic: SemanticIndex | None):
        self.library = library
        self.famous = famous
        self.semantic = semantic
        self.keyword = KeywordIndex(list(library.bibles.values()))
        self._plain_cache: dict[str, dict[int, str]] = {}

    def warm_up(self) -> None:
        """Do the one-off work up front so the first live search is instant."""
        for bible in self.library.bibles.values():
            self._plain_texts(bible)
        if self.semantic is not None and self.semantic.ready:
            self.semantic.search("warm up", limit=1)

    # ------------------------------------------------------------ helpers
    def _plain_texts(self, bible: Bible) -> dict[int, str]:
        cached = self._plain_cache.get(bible.id)
        if cached is None:
            cached = {k: _plain(t) for k, t in bible.texts.items()}
            self._plain_cache[bible.id] = cached
        return cached

    def _phrase_hits(self, query: str, keys: list[int]) -> set[int]:
        """Candidate verses that contain the typed words verbatim in some translation."""
        q = _plain(query)
        if len(q.split()) < 3:
            return set()
        hits = set()
        for bible in self.library.bibles.values():
            plain = self._plain_texts(bible)
            for k in keys:
                t = plain.get(k)
                if t and q in t:
                    hits.add(k)
        return hits

    def validate(self, ref: reference.Reference) -> reference.Reference | None:
        """Clamp a reference to verses that exist; None if it doesn't exist at all."""
        bible = self.library.any()
        if bible.last_chapter(ref.book) < ref.chapter:
            return None
        if ref.verse is None:
            return ref
        last = bible.last_verse(ref.book, ref.chapter)
        if ref.verse > last:
            return None
        end_ch = ref.end_chapter or ref.chapter
        end_v = ref.end_verse or ref.verse
        if end_ch == ref.chapter:
            end_v = min(end_v, last)
        elif bible.last_chapter(ref.book) < end_ch:
            end_ch, end_v = ref.chapter, last
        else:
            end_v = min(end_v, bible.last_verse(ref.book, end_ch))
        return reference.Reference(ref.book, ref.chapter, ref.verse, end_ch, end_v)

    # ------------------------------------------------------------ search
    def search(self, query: str, limit: int = 30) -> list[Result]:
        query = query.strip()
        if not query:
            return []
        results: dict[tuple, Result] = {}

        def add(ref: reference.Reference, score: float, source: str, note: str = "") -> None:
            r = Result(ref, score, {source}, note)
            existing = results.get(r.key)
            if existing:
                existing.score = max(existing.score, score) + 0.05
                existing.sources.add(source)
                existing.note = existing.note or note
            else:
                results[r.key] = r

        ref = reference.parse(query)
        if ref is not None:
            ref = self.validate(ref)
            if ref is not None:
                add(ref, 10.0, "reference")
                return list(results.values())

        for fref, fscore, name in self.famous.match(query):
            add(fref, 3.0 + fscore, "famous", name)

        # Word search and meaning search, blended per verse.
        blended: dict[int, float] = {}
        sources: dict[int, set[str]] = {}
        kw = self.keyword.search(query, limit=60)
        if kw:
            top = kw[0][1]
            for k, s in kw:
                blended[k] = blended.get(k, 0.0) + 0.55 * (s / top)
                sources.setdefault(k, set()).add("keyword")
        if self.semantic is not None and self.semantic.ready and len(query) >= 3:
            sem = self.semantic.search(query, limit=60)
            if sem:
                best = sem[0][1]
                floor = max(0.0, best - 0.25)
                for k, s in sem:
                    if s <= floor:
                        continue
                    blended[k] = blended.get(k, 0.0) + 0.6 * (s - floor) / (best - floor + 1e-9) * min(1.0, best / 0.7)
                    sources.setdefault(k, set()).add("meaning")
        candidates = sorted(blended, key=lambda k: -blended[k])[:80]
        for k in self._phrase_hits(query, candidates):
            blended[k] += 0.8
            sources[k].add("phrase")
        for k in candidates:
            if k in self.famous.popular_keys:
                blended[k] += 0.12
        for k in sorted(blended, key=lambda k: -blended[k])[:limit]:
            b, c, v = split_key(k)
            vref = reference.Reference(b, c, v, c, v)
            for src in sources[k]:
                add(vref, blended[k], src)

        ordered = sorted(results.values(), key=lambda r: -r.score)
        return ordered[:limit]

    def merge_ai(self, results: list[Result], ai_refs: list[tuple[reference.Reference, str]]) -> list[Result]:
        """Insert AI suggestions (already validated) near the top of the offline list."""
        by_key = {r.key: r for r in results}
        top_offline = max((r.score for r in results if "reference" not in r.sources), default=0.0)
        for rank, (ref, why) in enumerate(ai_refs):
            ref = self.validate(ref)
            if ref is None:
                continue
            score = max(top_offline, 3.0) + 1.0 - rank * 0.1
            key = Result(ref, 0).key
            if key in by_key:
                existing = by_key[key]
                existing.sources.add("ai")
                existing.score = max(existing.score, score)
                existing.note = existing.note or why
            else:
                single = Result(reference.Reference(ref.book, ref.chapter, ref.verse, ref.chapter, ref.verse), 0).key
                if single in by_key and not ref.is_range:
                    by_key[single].sources.add("ai")
                    by_key[single].score = max(by_key[single].score, score)
                    continue
                by_key[key] = Result(ref, score, {"ai"}, why)
        return sorted(by_key.values(), key=lambda r: -r.score)

    # ------------------------------------------------------------ text
    def passage_text(self, ref: reference.Reference, bible_id: str) -> list[tuple[int, int, str]]:
        """(chapter, verse, text) rows for a reference in the chosen translation."""
        bible = self.library.get(bible_id) or self.library.any()
        rows = []
        if ref.verse is None:
            for v in range(1, bible.last_verse(ref.book, ref.chapter) + 1):
                t = bible.text(ref.book, ref.chapter, v)
                if t:
                    rows.append((ref.chapter, v, t))
            return rows
        end_ch = ref.end_chapter or ref.chapter
        end_v = ref.end_verse or ref.verse
        start = verse_key(ref.book, ref.chapter, ref.verse)
        stop = verse_key(ref.book, end_ch, end_v)
        for i in range(bisect.bisect_left(bible.keys, start), bisect.bisect_right(bible.keys, stop)):
            k = bible.keys[i]
            _, c, v = split_key(k)
            rows.append((c, v, bible.texts[k]))
        return rows
