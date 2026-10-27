"""Online helper: ask Claude which verses the operator means.

Only used when an API key is configured and the internet is up. Every reference
Claude returns is checked against the local Bible text before it is shown, so
a wrong or made-up reference never reaches the screen. Offline results are
always shown first; AI suggestions are merged in when they arrive.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import anthropic

from . import books
from .reference import Reference

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You help a church media operator find Bible passages live during a service.
The operator types what the preacher just said or asked for: a paraphrase, a partial quote
from any English translation (KJV, NKJV, NIV, ESV, NLT, AMP, MSG, etc.), a story, a theme,
or a phrase misheard over a noisy sound system.

Return the passages the preacher most likely means, best match first (at most 5).
Use the standard Protestant 66-book canon and English verse numbering. Prefer the single
verse or short range that would be projected on screen. If the query names a story or a
theme, return the key verse(s) a pastor would typically read for it. Keep "why" under 12 words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "book": {"type": "string", "description": "Full English book name, e.g. '1 Corinthians'"},
                    "chapter": {"type": "integer"},
                    "verse_start": {"type": "integer"},
                    "verse_end": {"type": "integer"},
                    "why": {"type": "string"},
                },
                "required": ["book", "chapter", "verse_start", "verse_end", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


class AIUnavailable(Exception):
    """No key, no internet, or the service declined; offline search carries on."""


@dataclass
class AISuggestion:
    ref: Reference
    why: str


class AIResolver:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 12.0):
        self.model = model or DEFAULT_MODEL
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0) if api_key else None
        self._cache: dict[str, list[AISuggestion]] = {}
        self._offline_until = 0.0

    @property
    def configured(self) -> bool:
        return self._client is not None

    @property
    def online(self) -> bool:
        return self.configured and time.monotonic() >= self._offline_until

    def resolve(self, query: str) -> list[AISuggestion]:
        key = " ".join(query.lower().split())
        if key in self._cache:
            return self._cache[key]
        if self._client is None:
            raise AIUnavailable("No API key set")
        if time.monotonic() < self._offline_until:
            raise AIUnavailable("Offline")
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": query}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIConnectionError as exc:  # includes timeouts
            self._offline_until = time.monotonic() + 30  # don't hammer a dead connection mid-service
            raise AIUnavailable("No internet connection") from exc
        except anthropic.AuthenticationError as exc:
            raise AIUnavailable("API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            self._offline_until = time.monotonic() + 15
            raise AIUnavailable("Rate limited, retrying shortly") from exc
        except anthropic.APIStatusError as exc:
            raise AIUnavailable(f"AI service error ({exc.status_code})") from exc

        if response.stop_reason == "refusal":
            raise AIUnavailable("AI declined this query")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            items = json.loads(text)["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AIUnavailable("Unexpected AI response") from exc

        suggestions = []
        for item in items[:5]:
            book = books.find_book(str(item.get("book", "")))
            try:
                ch, v1, v2 = int(item["chapter"]), int(item["verse_start"]), int(item["verse_end"])
            except (KeyError, TypeError, ValueError):
                continue
            if book is None or ch < 1 or v1 < 1:
                continue
            v2 = max(v1, v2)
            suggestions.append(AISuggestion(Reference(book, ch, v1, ch, v2), str(item.get("why", ""))))
        self._cache[key] = suggestions
        return suggestions
