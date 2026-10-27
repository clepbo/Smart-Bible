"""Drive BibleShow (bibleshow.net) by keyboard, so its styling, translations and
NDI output are used unchanged.

Keys used, from BibleShow's manual:
    F5               focus the Reference textbox
    Enter            view the typed reference (e.g. "mt6.9")
    Ctrl+Shift+F10   show on screen  (global hotkey, works without focus)
    Ctrl+Shift+F8    hide            (global hotkey)
    Ctrl+Shift+Down  next verse      (global hotkey)
    Ctrl+Shift+Up    previous verse  (global hotkey)

All key sequences are configurable in Settings in case a BibleShow version differs.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

from . import books
from .reference import Reference

IS_WINDOWS = sys.platform == "win32"

# Reference formats offered in Settings. {book}=full name, {abbr}=short form.
FORMAT_PRESETS = {
    "John 3:16": "{book} {chapter}:{verse}",
    "John 3.16": "{book} {chapter}.{verse}",
    "jn3.16 (BibleShow shortcut style)": "{short}{chapter}.{verse}",
    "John 3 16": "{book} {chapter} {verse}",
}

# Short forms in the style of BibleShow's "mt6.9" example.
SHORT_FORMS = {
    1: "gn", 2: "ex", 3: "lv", 4: "nm", 5: "dt", 6: "js", 7: "jg", 8: "rt", 9: "1sm", 10: "2sm",
    11: "1kg", 12: "2kg", 13: "1ch", 14: "2ch", 15: "ezr", 16: "neh", 17: "est", 18: "jb",
    19: "ps", 20: "pr", 21: "ec", 22: "sg", 23: "is", 24: "jr", 25: "lm", 26: "ezk", 27: "dn",
    28: "hs", 29: "jl", 30: "am", 31: "ob", 32: "jnh", 33: "mc", 34: "nam", 35: "hab",
    36: "zph", 37: "hg", 38: "zch", 39: "mal", 40: "mt", 41: "mk", 42: "lk", 43: "jn",
    44: "ac", 45: "rm", 46: "1co", 47: "2co", 48: "gl", 49: "eph", 50: "php", 51: "col",
    52: "1th", 53: "2th", 54: "1tm", 55: "2tm", 56: "ti", 57: "phm", 58: "hb", 59: "jm",
    60: "1pt", 61: "2pt", 62: "1jn", 63: "2jn", 64: "3jn", 65: "jd", 66: "rv",
}


@dataclass
class BibleShowSettings:
    window_title: str = "BibleShow"
    reference_format: str = "{book} {chapter}:{verse}"
    focus_keys: str = "{F5}"
    view_keys: str = "{ENTER}"
    show_after_view: bool = True
    show_keys: str = "^+{F10}"
    hide_keys: str = "^+{F8}"
    next_keys: str = "^+{DOWN}"
    prev_keys: str = "^+{UP}"
    step_delay_ms: int = 60
    return_focus: bool = True


class BibleShowError(Exception):
    pass


def format_reference(ref: Reference, template: str) -> str:
    """Text to type into BibleShow's Reference box (first verse of a range)."""
    verse = ref.verse or 1
    return template.format(
        book=books.NAMES[ref.book],
        abbr=books.ABBREVIATIONS[ref.book],
        short=SHORT_FORMS[ref.book],
        chapter=ref.chapter,
        verse=verse,
    )


def escape_keys(text: str) -> str:
    """Escape characters that pywinauto's send_keys treats as commands."""
    return "".join("{%s}" % c if c in "+^%~(){}[]" else c for c in text)


class BibleShowDriver:
    def __init__(self, settings: BibleShowSettings):
        self.settings = settings

    # ------------------------------------------------------------ windows
    def _find_window(self):
        if not IS_WINDOWS:
            raise BibleShowError("BibleShow control only works on Windows")
        from pywinauto import Desktop

        wanted = self.settings.window_title.lower()
        for win in Desktop(backend="win32").windows(visible_only=True):
            try:
                title = win.window_text()
            except Exception:
                continue
            if wanted in title.lower() and "smart bible" not in title.lower():
                return win
        raise BibleShowError(f"Could not find a window titled '{self.settings.window_title}'. Is BibleShow running?")

    def _send(self, keys: str) -> None:
        from pywinauto.keyboard import send_keys

        send_keys(keys, pause=0.01, with_spaces=True)

    def _pause(self) -> None:
        time.sleep(self.settings.step_delay_ms / 1000)

    def is_running(self) -> bool:
        try:
            self._find_window()
            return True
        except BibleShowError:
            return False
        except Exception:
            return False

    # ------------------------------------------------------------ actions
    def send_reference(self, ref: Reference, go_live: bool | None = None) -> str:
        """Type the reference into BibleShow and (optionally) put it on screen."""
        s = self.settings
        text = format_reference(ref, s.reference_format)
        win = self._find_window()
        if win.is_minimized():
            win.restore()
        win.set_focus()
        self._pause()
        self._send(s.focus_keys)
        self._pause()
        self._send("^a" + escape_keys(text))
        self._pause()
        self._send(s.view_keys)
        if s.show_after_view if go_live is None else go_live:
            self._pause()
            self._send(s.show_keys)
        return text

    def refocus(self, hwnd: int) -> None:
        """Give keyboard focus back to Smart Bible so the operator can keep typing."""
        if not IS_WINDOWS or not self.settings.return_focus:
            return
        from pywinauto.controls.hwndwrapper import HwndWrapper

        self._pause()
        HwndWrapper(hwnd).set_focus()

    def hotkey(self, which: str) -> None:
        """Send one of BibleShow's global hotkeys: 'show', 'hide', 'next', 'prev'."""
        if not IS_WINDOWS:
            raise BibleShowError("BibleShow control only works on Windows")
        keys = {
            "show": self.settings.show_keys,
            "hide": self.settings.hide_keys,
            "next": self.settings.next_keys,
            "prev": self.settings.prev_keys,
        }[which]
        self._send(keys)
