"""Locating data files and assembling the search engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .bible import Library
from .famous import FamousIndex
from .search import SearchEngine
from .semantic import INDEX_FILE, SemanticIndex


def app_root() -> Path:
    """Folder holding the bundled ``data`` directory (source tree or PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def user_dir() -> Path:
    """Per-user writable folder: %APPDATA%\\SmartBible on Windows."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    path = Path(base) / "SmartBible"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_bible_dir() -> Path:
    path = user_dir() / "bibles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_semantic_index() -> SemanticIndex:
    data = app_root() / "data"
    bundled = data / "index" / INDEX_FILE
    index_path = bundled if bundled.exists() else user_dir() / "index" / INDEX_FILE
    model_dir = data / "models" if (data / "models").exists() else user_dir() / "models"
    return SemanticIndex(model_dir, index_path)


def build_engine(use_semantic: bool = True) -> SearchEngine:
    data = app_root() / "data"
    library = Library([data / "bibles", user_bible_dir()])
    if not library.bibles:
        raise RuntimeError(f"No Bible translations found in {data / 'bibles'}")
    famous = FamousIndex(data / "famous.json")
    semantic = None
    if use_semantic:
        semantic = make_semantic_index()
        try:
            semantic.load()
        except Exception:
            semantic.vectors = None
    return SearchEngine(library, famous, semantic)
