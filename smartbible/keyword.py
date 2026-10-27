"""Word-based search (BM25) over all loaded translations at once.

Each verse is one document made of the words of *every* translation, so a
query phrased like the NIV ("love is patient") still finds the verse even
though the KJV says "charity suffereth long".
"""

from __future__ import annotations

import bisect
import difflib
import re
from collections import Counter

import numpy as np

from .bible import Bible

STOPWORDS = frozenset(
    """a an and are as at be but by for from had has have he her his i if in into is it its
    me my no not of on or our she so than that the their them then there these they this
    those thou thee thy thine to unto us was we were what when where which who whom will
    with ye you your shall hath doth did do does o oh about verse bible scripture
    says said say talks talking passage""".split()
)

_ARCHAIC = {
    "saith": "say", "spake": "speak", "goeth": "go", "cometh": "come", "doeth": "do",
    "hast": "have", "hath": "have", "art": "are", "shew": "show", "shewed": "show",
    "giveth": "give", "maketh": "make", "taketh": "take", "knoweth": "know",
    "loveth": "love", "believeth": "believe", "seeketh": "seek", "lieth": "lie",
}

_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


def stem(word: str) -> str:
    """A tiny English + Elizabethan English suffix stripper.

    Final "e" is always dropped so love/loved/loving/loveth all become "lov".
    """
    word = _ARCHAIC.get(word, word)
    if word.endswith("'s"):
        word = word[:-2]
    for suffix in ("eth", "est", "ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if len(word) >= 4 and word[-1] == word[-2] and word[-1] not in "ls":
                word = word[:-1]  # "running" -> "run"
            break
    else:
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith(("ches", "shes", "sses", "xes")):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    words = _WORD.findall(text.lower().replace("’", "'"))
    if not keep_stopwords:
        words = [w for w in words if w not in STOPWORDS]
    return [stem(w) for w in words]


class KeywordIndex:
    def __init__(self, bibles: list[Bible], k1: float = 1.2, b: float = 0.6):
        all_keys = sorted({k for bible in bibles for k in bible.keys})
        self.keys = np.array(all_keys, dtype=np.int64)
        key_pos = {k: i for i, k in enumerate(all_keys)}

        vocab: dict[str, int] = {}
        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []
        doc_len = np.zeros(len(all_keys), dtype=np.float32)
        n_translations = max(1, len(bibles))
        for k in all_keys:
            counts: Counter[str] = Counter()
            for bible in bibles:
                text = bible.texts.get(k)
                if text:
                    counts.update(set(tokenize(text)))
            d = key_pos[k]
            doc_len[d] = sum(counts.values()) / n_translations
            for term, tf in counts.items():
                t = vocab.setdefault(term, len(vocab))
                rows.append(t)
                cols.append(d)
                vals.append(tf / n_translations)  # fraction of translations using the word

        order = np.lexsort((np.array(cols), np.array(rows)))
        self._post_docs = np.array(cols, dtype=np.int32)[order]
        self._post_tf = np.array(vals, dtype=np.float32)[order]
        term_ids = np.array(rows, dtype=np.int32)[order]
        self._offsets = np.searchsorted(term_ids, np.arange(len(vocab) + 1))
        self.vocab = vocab
        self._sorted_terms = sorted(vocab)
        self._by_initial: dict[str, list[str]] = {}
        for term in self._sorted_terms:
            self._by_initial.setdefault(term[0], []).append(term)
        n_docs = len(all_keys)
        df = np.diff(self._offsets).astype(np.float32)
        self._idf = np.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        avg = doc_len.mean() if n_docs else 1.0
        self._norm = k1 * (1 - b + b * doc_len / avg)
        self._k1 = k1

    def correct(self, term: str) -> str | None:
        """Closest known word for a misspelt one ("prodical" -> "prodig")."""
        if len(term) < 4:
            return None
        pool = self._by_initial.get(term[0], [])
        pool = [t for t in pool if abs(len(t) - len(term)) <= 2]
        match = difflib.get_close_matches(term, pool, n=1, cutoff=0.75)
        return match[0] if match else None

    def _expand_prefix(self, prefix: str, limit: int = 8) -> list[int]:
        i = bisect.bisect_left(self._sorted_terms, prefix)
        out = []
        while i < len(self._sorted_terms) and self._sorted_terms[i].startswith(prefix):
            out.append(self.vocab[self._sorted_terms[i]])
            i += 1
        # most common completions first
        out.sort(key=lambda t: -(self._offsets[t + 1] - self._offsets[t]))
        return out[:limit]

    def search(self, query: str, limit: int = 50, prefix_last: bool = True) -> list[tuple[int, float]]:
        raw_words = _WORD.findall(query.lower())
        terms = tokenize(query)
        if not terms:
            return []
        scores = np.zeros(len(self.keys), dtype=np.float32)
        last_is_partial = prefix_last and raw_words and not query.endswith(" ")
        for idx, term in enumerate(terms):
            ids = []
            is_last_partial = last_is_partial and idx == len(terms) - 1
            if term in self.vocab:
                ids.append(self.vocab[term])
            elif not is_last_partial:
                fixed = self.correct(term)
                if fixed:
                    ids.append(self.vocab[fixed])
            if last_is_partial and idx == len(terms) - 1 and len(term) >= 3:
                ids.extend(t for t in self._expand_prefix(term) if t not in ids)
            for n, t in enumerate(ids):
                lo, hi = self._offsets[t], self._offsets[t + 1]
                docs = self._post_docs[lo:hi]
                tf = self._post_tf[lo:hi]
                w = 1.0 if n == 0 and term in self.vocab else 0.6  # prefix completions count less
                scores[docs] += w * self._idf[t] * tf * (self._k1 + 1) / (tf + self._norm[docs])
        limit = min(limit, int((scores > 0).sum()))
        if limit == 0:
            return []
        top = np.argpartition(-scores, limit - 1)[:limit]
        top = top[np.argsort(-scores[top])]
        return [(int(self.keys[i]), float(scores[i])) for i in top]
