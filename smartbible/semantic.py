"""Meaning-based search: verse embeddings + cosine similarity, fully offline.

The embedding model (bge-small, ~65 MB ONNX) runs on the CPU. Verse vectors are
pre-computed once (``python scripts/build_index.py``, ~5-10 minutes) and saved
as ``embeddings.npz``; at runtime only the query is embedded (~10-20 ms).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .bible import Bible

MODEL_NAME = "BAAI/bge-small-en-v1.5"
INDEX_FILE = "embeddings.npz"


class SemanticIndex:
    def __init__(self, model_dir: Path, index_path: Path):
        self.model_dir = model_dir
        self.index_path = index_path
        self._model = None
        self._model_lock = threading.Lock()
        self.keys: np.ndarray | None = None
        self.vectors: np.ndarray | None = None
        self.source_id: str | None = None

    # ------------------------------------------------------------ model
    def _get_model(self, allow_download: bool = False):
        with self._model_lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self.model_dir.mkdir(parents=True, exist_ok=True)
                kwargs = {} if allow_download else {"local_files_only": True}
                if not allow_download:
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")
                self._model = TextEmbedding(MODEL_NAME, cache_dir=str(self.model_dir), **kwargs)
            return self._model

    def model_available(self) -> bool:
        try:
            self._get_model()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------ index
    @property
    def ready(self) -> bool:
        return self.vectors is not None

    def load(self) -> bool:
        if not self.index_path.exists():
            return False
        data = np.load(self.index_path, allow_pickle=False)
        self.keys = data["keys"]
        self.vectors = data["vectors"].astype(np.float32)
        self.source_id = str(data["source"]) if "source" in data else None
        return True

    def build(
        self,
        bible: Bible,
        progress: Callable[[int, int], None] | None = None,
        allow_download: bool = False,
        batch_size: int = 256,
    ) -> None:
        model = self._get_model(allow_download=allow_download)
        keys = np.array(bible.keys, dtype=np.int64)
        texts = [bible.texts[k] for k in bible.keys]
        chunks = []
        done = 0
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            chunks.append(np.array(list(model.embed(batch, batch_size=batch_size)), dtype=np.float32))
            done += len(batch)
            if progress:
                progress(done, len(texts))
        vectors = np.vstack(chunks)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp.npz")
        np.savez(tmp, keys=keys, vectors=vectors.astype(np.float16), source=np.array(bible.id))
        tmp.replace(self.index_path)
        self.keys, self.vectors, self.source_id = keys, vectors, bible.id

    # ------------------------------------------------------------ query
    def search(self, query: str, limit: int = 50) -> list[tuple[int, float]]:
        if not self.ready:
            return []
        model = self._get_model()
        q = np.array(next(iter(model.query_embed(query))), dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-12
        scores = self.vectors @ q
        limit = min(limit, len(scores))
        top = np.argpartition(-scores, limit - 1)[:limit]
        top = top[np.argsort(-scores[top])]
        return [(int(self.keys[i]), float(scores[i])) for i in top]
