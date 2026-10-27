import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from smartbible import books, reference
from smartbible.ai import AIResolver, AIUnavailable
from smartbible.bible import load_csv, load_zefania
from smartbible.bibleshow import FORMAT_PRESETS, escape_keys, format_reference
from smartbible.engine import app_root, build_engine
from smartbible.famous import FamousIndex
from smartbible.keyword import stem
from smartbible.reference import Reference


@pytest.fixture(scope="session")
def engine():
    return build_engine(use_semantic=False)


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Jer 29:11", "Jeremiah 29:11"),
        ("john 3 16", "John 3:16"),
        ("jn3.16", "John 3:16"),
        ("mt6.9", "Matthew 6:9"),
        ("1 cor 13:4-7", "1 Corinthians 13:4-7"),
        ("psalm 23", "Psalms 23"),
        ("rom 8 28 to 30", "Romans 8:28-30"),
        ("gen 1:1-2:3", "Genesis 1:1-2:3"),
        ("John chapter 3 verse 16", "John 3:16"),
        ("first corinthians thirteen four", "1 Corinthians 13:4"),
        ("psalm one hundred and nineteen", "Psalms 119"),
        ("psalm twenty-three", "Psalms 23"),
        ("I John 1:9", "1 John 1:9"),
        ("1st john 4 8", "1 John 4:8"),
        ("song of solomon 2 4", "Song of Solomon 2:4"),
        ("romans eight twenty eight", "Romans 8:28"),
    ],
)
def test_reference_parsing(query, expected):
    ref = reference.parse(query)
    assert ref is not None and ref.display() == expected


@pytest.mark.parametrize("query", ["love is patient", "jesus wept", "the prodigal son", "", "is love kind"])
def test_non_references(query):
    assert reference.parse(query) is None


def test_book_lookup():
    assert books.find_book("Philipp") == 50
    assert books.find_book("phm") == 57
    assert books.find_book("Revelations") == 66
    assert books.find_book("song of songs") == 22
    assert books.find_book("xyz") is None


def test_stemming_is_consistent():
    assert len({stem(w) for w in ["love", "loved", "loveth", "loving", "loves"]}) == 1
    assert len({stem(w) for w in ["believe", "believeth", "believing"]}) == 1


def test_famous_passages_exist_in_kjv(engine):
    famous = FamousIndex(app_root() / "data" / "famous.json")
    kjv = engine.library.get("KJV")
    for p in famous.passages:
        r = p.ref
        assert kjv.has(r.book, r.chapter, r.verse), r.display()
        assert kjv.has(r.book, r.end_chapter or r.chapter, r.end_verse or r.verse), r.display()


def test_bundled_translations(engine):
    assert {"KJV", "BSB", "NHEB", "ASV", "BBE", "YLT"} <= set(engine.library.ids())
    assert engine.library.get("BSB").text(24, 29, 11).startswith("For I know the plans")


def test_reference_query_returns_exact_verse(engine):
    results = engine.search("jn 3 16")
    assert results[0].ref.display() == "John 3:16"
    assert engine.search("John 99:1") == [] or "reference" not in engine.search("John 99:1")[0].sources


def test_range_is_clamped(engine):
    ref = engine.validate(reference.parse("psalm 117:1-10"))
    assert ref.display() == "Psalms 117:1-2"


def test_offline_word_search(engine):
    for query, expected in [
        ("charity suffereth long", "1 Corinthians 13:4"),
        ("plans to prosper you", "Jeremiah 29:11"),
        ("prodical son", "Luke 15:11-32"),
        ("for god so loved", "John 3:16"),
    ]:
        top = [r.ref.display() for r in engine.search(query)[:3]]
        assert expected in top, (query, top)


def test_passage_text(engine):
    rows = engine.passage_text(reference.parse("1 cor 13:4-7"), "KJV")
    assert [v for _, v, _ in rows] == [4, 5, 6, 7]


def test_user_csv_and_zefania(tmp_path):
    csv_file = tmp_path / "MYV.csv"
    csv_file.write_text("book,chapter,verse,text\nJohn,3,16,\"For God, so loved\"\n43,11,35,Jesus wept.\n")
    bible = load_csv(csv_file)
    assert bible.text(43, 3, 16) == "For God, so loved"
    assert bible.text(43, 11, 35) == "Jesus wept."

    xml = tmp_path / "ZEF.xml"
    xml.write_text(
        '<XMLBIBLE biblename="Test"><BIBLEBOOK bnumber="43"><CHAPTER cnumber="11">'
        '<VERS vnumber="35">Jesus wept.</VERS></CHAPTER></BIBLEBOOK></XMLBIBLE>'
    )
    assert load_zefania(xml).text(43, 11, 35) == "Jesus wept."


def test_bibleshow_formats():
    ref = Reference(40, 6, 9, 6, 13)
    out = {label: format_reference(ref, t) for label, t in FORMAT_PRESETS.items()}
    assert out["John 3:16"] == "Matthew 6:9"
    assert out["jn3.16 (BibleShow shortcut style)"] == "mt6.9"
    assert escape_keys("a+b(c)") == "a{+}b{(}c{)}"


# ---------------------------------------------------------------- AI


class _FakeClaude(BaseHTTPRequestHandler):
    requests: list = []
    reply: dict = {}

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeClaude.requests.append((dict(self.headers), body))
        payload = json.dumps(_FakeClaude.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_claude():
    server = HTTPServer(("127.0.0.1", 0), _FakeClaude)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _FakeClaude.requests = []
    yield server
    server.shutdown()


def _message(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def test_ai_resolver_parses_and_validates(fake_claude, engine):
    _FakeClaude.reply = _message(
        json.dumps(
            {
                "results": [
                    {"book": "Jeremiah", "chapter": 29, "verse_start": 11, "verse_end": 11, "why": "plans to prosper"},
                    {"book": "Hezekiah", "chapter": 1, "verse_start": 1, "verse_end": 1, "why": "not a book"},
                    {"book": "John", "chapter": 99, "verse_start": 1, "verse_end": 1, "why": "no such chapter"},
                ]
            }
        )
    )
    ai = AIResolver("test-key")
    ai._client = ai._client.with_options(base_url=f"http://127.0.0.1:{fake_claude.server_port}")
    suggestions = ai.resolve("God has good plans for my future")
    assert [s.ref.display() for s in suggestions] == ["Jeremiah 29:11", "John 99:1"]

    headers, body = _FakeClaude.requests[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in headers.get("anthropic-beta", "")
    assert body["output_config"]["format"]["type"] == "json_schema"

    # Invalid references are dropped when merged into the result list.
    merged = engine.merge_ai(engine.search("God has good plans for my future"), [(s.ref, s.why) for s in suggestions])
    assert merged[0].ref.display() == "Jeremiah 29:11"
    assert all(r.ref.display() != "John 99:1" for r in merged)

    # Same query again is served from cache.
    ai.resolve("god has good plans  for my future")
    assert len(_FakeClaude.requests) == 1


def test_ai_refusal_and_offline(fake_claude):
    _FakeClaude.reply = _message("", stop_reason="refusal")
    ai = AIResolver("test-key")
    ai._client = ai._client.with_options(base_url=f"http://127.0.0.1:{fake_claude.server_port}")
    with pytest.raises(AIUnavailable):
        ai.resolve("anything")

    offline = AIResolver("test-key", timeout=1)
    offline._client = offline._client.with_options(base_url="http://127.0.0.1:9")
    with pytest.raises(AIUnavailable, match="internet"):
        offline.resolve("anything")
    assert not offline.online  # backs off instead of retrying every keystroke


def test_ai_without_key():
    ai = AIResolver("")
    assert not ai.configured
    with pytest.raises(AIUnavailable):
        ai.resolve("love")
