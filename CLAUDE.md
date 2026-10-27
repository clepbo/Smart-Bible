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

## Open questions to ask the user before building
- How do they project: BibleShow straight to screen, or via vMix/OBS?
- Which translations do they use?
- Is venue internet reliable enough to depend on, or must search be fully offline?
- Windows desktop app vs. web app (runs in browser on the media PC)?

## Suggested approach
- Start with a working prototype: local Bible JSON + embedding-based semantic search + reference parser,
  simple UI, and one projection mode. Then iterate.
