"""Measure offline search quality on tests/eval_queries.py.

    python scripts/eval_search.py [--top 5] [--no-semantic] [-v]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartbible import reference  # noqa: E402
from smartbible.engine import build_engine  # noqa: E402
from tests.eval_queries import QUERIES  # noqa: E402


def hit_rank(results, accepted: list[str]) -> int | None:
    wanted = [reference.parse(a) for a in accepted]
    for rank, r in enumerate(results, start=1):
        for w in wanted:
            if (r.ref.book, r.ref.chapter) != (w.book, w.chapter):
                continue
            if w.verse is None or r.ref.verse == w.verse:
                return rank
            end = r.ref.end_verse or r.ref.verse or 0
            if r.ref.verse and r.ref.verse <= w.verse <= end and r.ref.is_range and w.end_verse in (None, w.verse):
                return rank
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--no-semantic", action="store_true")
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()

    engine = build_engine(use_semantic=not args.no_semantic)
    engine.warm_up()
    passed = top1 = 0
    times = []
    for query, accepted in QUERIES:
        t = time.perf_counter()
        results = engine.search(query, limit=20)
        times.append(time.perf_counter() - t)
        rank = hit_rank(results, accepted)
        ok = rank is not None and rank <= args.top
        passed += ok
        top1 += rank == 1
        if args.v or not ok:
            shown = ", ".join(r.ref.display() for r in results[:5])
            print(f"{'PASS' if ok else 'FAIL'} [{rank}] {query!r} -> {shown}")
    n = len(QUERIES)
    print(f"\nTop-{args.top}: {passed}/{n} ({passed / n:.0%})   Top-1: {top1}/{n} ({top1 / n:.0%})")
    times.sort()
    print(f"Median {times[n // 2] * 1000:.0f} ms, worst {times[-1] * 1000:.0f} ms per query")


if __name__ == "__main__":
    main()
