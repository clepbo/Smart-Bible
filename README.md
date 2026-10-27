# Smart Bible

Find the verse the preacher means, fast, and put it on screen through **BibleShow**.

Type a reference (`jn 3 16`, `1 cor 13:4-7`), a quote from any translation
(`love is patient`, `charity suffereth long`), a story (`the prodigal son`,
`Peter denies Jesus`) or just what the sermon is about (`God's plans to prosper us`).
Press **Enter** and Smart Bible types the reference into BibleShow for you, so your
existing BibleShow look, translations and **NDI output** keep working unchanged.

- **Works offline.** Reference parsing, word search across 6 public-domain translations
  and meaning-based search all run on the media PC. No internet needed mid-service.
- **Smarter when online.** With an Anthropic API key, Claude also suggests passages for
  vague or misheard queries. Its answers are checked against the Bible text before they're
  shown, and offline results appear immediately either way.
- **Fast.** Typical search takes about 50 ms.

## Install (Windows)

1. Open the repository's **Actions** tab → **Build Windows app** → the latest successful run,
   and download **SmartBible-windows** (or download it from **Releases** once one is published).
2. Unzip it anywhere, e.g. `C:\SmartBible`.
3. Run `SmartBible\SmartBible.exe`. Windows SmartScreen may warn about an unknown publisher.
   Click **More info → Run anyway**.

## First-time setup

1. Start **BibleShow** as usual.
2. In Smart Bible, open **Settings** and click **Test with John 3:16**.
   - If BibleShow shows John 3:16, you're done.
   - If not, change **Reference format typed into BibleShow** (e.g. to `jn3.16` style, BibleShow's
     own shortcut format) and test again.
   - Untick **Put the verse on screen straight away** if you'd rather load the verse and
     show it yourself from BibleShow.
3. Optional, for online AI help: paste an Anthropic API key (from console.anthropic.com).
   Without a key everything still works offline.

## Using it live

| Key | Action |
|---|---|
| type | results update as you type |
| ↑ / ↓ | move through results |
| **Enter** | send the selected passage to BibleShow and show it |
| Shift+Enter | load in BibleShow without showing |
| Ctrl+↓ / Ctrl+↑ | next / previous verse in BibleShow (step through a range) |
| F8 | hide the verse in BibleShow |
| Esc | clear the search box |
| F2 / Ctrl+L | jump back to the search box |

For a range like 1 Corinthians 13:4-7, Enter shows verse 4. Then press Ctrl+↓ to step through.

The status bar shows whether BibleShow is running and whether the AI is online. If the
internet drops, the AI indicator turns orange and offline search carries on by itself.

## Translations

Bundled (public domain): **KJV, BSB** (Berean Standard Bible, close to NIV wording),
**NHEB** (New Heart English Bible, World English Bible family), **ASV, BBE, YLT**.
All of them are searched at once, so modern and KJV wording both work.

**What appears on screen comes from BibleShow**, in whatever translation you've selected
there (NIV, NKJV, AMP, …). Smart Bible only finds the reference. The preview pane in Smart
Bible shows the bundled translations.

To search and preview with a licensed translation too, put a copy you're permitted to use
in `%APPDATA%\SmartBible\bibles\` and restart. Supported formats:

- CSV: `book,chapter,verse,text` (book as name or number 1-66)
- Zefania XML
- JSON: `{"id": "NIV", "name": "...", "verses": [[book, chapter, verse, "text"], ...]}`

## How search works

1. **Reference parser.** Handles typed and spoken forms: `jn3.16`, `john chapter 3 verse 16`,
   `first corinthians thirteen four`, `psalm one hundred and nineteen`.
2. **Well-known passages** (`data/famous.json`). About 300 well-known passages with their nicknames
   and famous lines ("the armour of God", "the great commission"), with typo tolerance ("prodical son").
3. **Word search.** BM25 over all translations together, with old-English-aware stemming
   (loveth/loved/loving), spelling correction, and completion of the word you're still typing.
4. **Meaning search.** A small embedding model (bge-small, ONNX, CPU-only) over every BSB verse.
5. **AI (optional, online).** Claude suggests references for fuzzy queries. Unknown books or
   chapters are dropped before display.

On the test set (`tests/eval_queries.py`, 70 operator-style queries) the right passage is in
the top 5 every time, and first 97% of the time, without internet.

## Building from source

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/build_index.py      # downloads the model, embeds all verses (~10 min, once)
python smartbible_app.py           # run
python -m pytest tests             # tests
python scripts/eval_search.py      # search-quality report
pyinstaller --noconfirm smartbible.spec   # dist\SmartBible\SmartBible.exe
```

`scripts/fetch_bibles.py` re-downloads the public-domain texts into `data/bibles/`.
