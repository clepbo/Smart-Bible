"""Download the embedding model and pre-compute verse vectors for offline search.

    python scripts/build_index.py            # uses BSB (modern wording)
    python scripts/build_index.py --bible KJV

Writes data/models/ (the ONNX model) and data/index/embeddings.npz.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from smartbible.bible import load_file  # noqa: E402
from smartbible.semantic import INDEX_FILE, SemanticIndex  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bible", default="BSB")
    args = parser.parse_args()

    bible = load_file(ROOT / "data" / "bibles" / f"{args.bible}.json.gz")
    index = SemanticIndex(ROOT / "data" / "models", ROOT / "data" / "index" / INDEX_FILE)
    started = time.time()

    def progress(done: int, total: int) -> None:
        print(f"\r  {done}/{total} verses ({time.time() - started:.0f}s)", end="", flush=True)

    print(f"Embedding {bible.name}...")
    index.build(bible, progress=progress, allow_download=True)
    print(f"\nSaved {index.index_path}")


if __name__ == "__main__":
    main()
