"""User settings, saved as JSON in %APPDATA%\\SmartBible\\settings.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields

from .ai import DEFAULT_MODEL
from .bibleshow import BibleShowSettings
from .engine import user_dir

OUTPUT_BIBLESHOW = "bibleshow"
OUTPUT_CLIPBOARD = "clipboard"


@dataclass
class Settings:
    translation: str = "KJV"
    output: str = OUTPUT_BIBLESHOW
    ai_enabled: bool = True
    api_key: str = ""
    ai_model: str = DEFAULT_MODEL
    font_size: int = 13
    bibleshow: BibleShowSettings = field(default_factory=BibleShowSettings)

    @staticmethod
    def path():
        return user_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known and k != "bibleshow"}
        bs_known = {f.name for f in fields(BibleShowSettings)}
        bs = BibleShowSettings(**{k: v for k, v in data.get("bibleshow", {}).items() if k in bs_known})
        return cls(**values, bibleshow=bs)

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(self.path())
