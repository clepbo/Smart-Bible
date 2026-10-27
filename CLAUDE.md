# Project: Smart Scripture Search & Projection (companion to BibleShow)

## Goal
Build a tool that lets a church media operator type a natural-language query
("the verse about God's plans to prosper us", "love is patient", "where Jesus wept")
and get the accurate scripture reference + text, then project it in one click, live during service.

## Background / decisions already made
- The user currently uses **BibleShow** (bibleshow.net, by Miodrag Rechesan). It is free,
  Windows-only, and closed source, so we cannot modify it. Its built-in search is keyword-only
  and not smart enough.
- github.com/vinceau/bibleshow was reviewed and rejected: unrelated hobby project with the same name,
  no license, no smart search. Build fresh instead.
- Plain Google search was considered but rejected as the main engine: it returns web pages, not
  verse references. Use **meaning-based (semantic) search over a local Bible text** instead,
  optionally with an LLM to resolve fuzzy queries. Google/web search can be an optional fallback.
- **Must work offline or degrade gracefully.** Venue internet (Nigeria) may be unreliable mid-service.
- Must be fast: the operator is searching live while a preacher is speaking.

## Core features (v1)
1. Search box accepting natural language, partial quotes, themes, or references ("Jer 29:11", "john 3 16").
2. Ranked results showing reference + verse text, with keyboard navigation.
3. One-click / Enter to project the selected verse (and support verse ranges, e.g. 1 Cor 13:4-7).
4. Multiple translations, switchable.

## Projection modes (pick based on user's setup — see open questions)
- **A. vMix / OBS output:** push verse text to a title/lower-third (vMix API / XML / OBS text source or browser source).
- **B. Drive BibleShow:** automate typing the reference into BibleShow's reference box (e.g. AutoHotkey / pywinauto),
  so existing BibleShow styling is kept.
- **C. Standalone:** the tool has its own full-screen projection window with custom styling.

## Bible text / licensing
- Public-domain translations (KJV, WEB, ASV) can be bundled freely.
- Modern translations (NIV, NKJV, ESV, AMP, etc.) are copyrighted: need licensed access or the church's own permitted copy.

## User's answers (settled)
- Projection: **BibleShow straight to screen**; sometimes BibleShow's NDI output feeds other software.
  → We use mode B (drive BibleShow by keyboard), so BibleShow keeps styling, translations and NDI.
- Translations: all major English ones. BibleShow displays the licensed text; we only find references.
  Bundled for search/preview: KJV, BSB, NHEB, ASV, BBE, YLT (public domain). Users can add licensed
  copies (CSV / Zefania XML / JSON) in %APPDATA%\SmartBible\bibles.
- Internet: online + offline both fine, but it must be smart. → Offline hybrid search always;
  Claude (online, optional API key) merges in suggestions, validated against local text.
- Platform: **Windows desktop app** (PySide6, packaged with PyInstaller; built by GitHub Actions on windows-latest).

## Architecture
- `smartbible/reference.py`: reference parser (typed + spoken numbers). `books.py`: book names/aliases.
- `smartbible/search.py`: `SearchEngine` fuses reference, `famous.py` (data/famous.json nicknames),
  `keyword.py` (BM25 over all translations), `semantic.py` (bge-small ONNX embeddings over BSB).
- `smartbible/ai.py`: Claude resolver (structured JSON output, refusal fallbacks, offline back-off).
- `smartbible/bibleshow.py`: keyboard driver via pywinauto. BibleShow keys (from its manual): F5 focus
  reference box, Enter view, Ctrl+Shift+F10 show, Ctrl+Shift+F8 hide, Ctrl+Shift+Down/Up next/prev.
- `smartbible/ui.py`: main window. `smartbible_app.py --self-test out.json` is the headless CI check.
- Quality: `python scripts/eval_search.py` (tests/eval_queries.py). Keep top-5 at 100% when changing ranking.

## Not verified yet / next ideas
- The BibleShow driver has not been tried against a real BibleShow install (built from its manual).
  The Settings "Test with John 3:16" button exists for on-site calibration.
- Ideas: global hotkey to bring Smart Bible to front, service history/playlist, direct NDI/OBS output.
