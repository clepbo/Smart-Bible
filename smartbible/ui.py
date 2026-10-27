"""The Smart Bible desktop window (PySide6)."""

from __future__ import annotations

import html
import sys
import threading
import traceback

from PySide6.QtCore import QEvent, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QFont, QKeySequence, QPalette, QShortcut, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .ai import AIResolver, AIUnavailable
from .bibleshow import FORMAT_PRESETS, BibleShowDriver, BibleShowError, format_reference
from .config import OUTPUT_BIBLESHOW, OUTPUT_CLIPBOARD, Settings
from .engine import build_engine, user_bible_dir
from .reference import Reference
from .search import SOURCE_LABELS, Result, SearchEngine

SEARCH_DELAY_MS = 120
AI_DELAY_MS = 650


# ---------------------------------------------------------------- workers


class _Signals(QObject):
    done = Signal(object, object)  # (token, payload)
    failed = Signal(object, str)
    progress = Signal(int, int)


class Task(QRunnable):
    """Run fn in the thread pool and report back on the UI thread."""

    def __init__(self, token, fn, *args):
        super().__init__()
        self.token, self.fn, self.args = token, fn, args
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(*self.args)
        except AIUnavailable as exc:
            self.signals.failed.emit(self.token, str(exc))
        except Exception as exc:  # report, never crash the live app
            traceback.print_exc()
            self.signals.failed.emit(self.token, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.done.emit(self.token, result)


# ---------------------------------------------------------------- result list


class ResultDelegate(QStyledItemDelegate):
    """Draws each result as a bold reference line plus a verse preview."""

    def _doc(self, option, index) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(index.data(Qt.UserRole + 1) or "")
        doc.setTextWidth(max(100, option.rect.width() - 12))
        return doc

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        doc = self._doc(option, index)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        if option.state & QStyle.State_Selected:
            ctx.palette.setColor(QPalette.Text, option.palette.color(QPalette.HighlightedText))
        painter.save()
        painter.translate(option.rect.left() + 6, option.rect.top() + 4)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        doc = self._doc(option, index)
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + 8)


# ---------------------------------------------------------------- settings


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Bible settings")
        self.settings = settings
        bs = settings.bibleshow
        layout = QVBoxLayout(self)

        out_box = QGroupBox("Output")
        out = QFormLayout(out_box)
        self.output = QComboBox()
        self.output.addItem("Send to BibleShow", OUTPUT_BIBLESHOW)
        self.output.addItem("Copy reference to clipboard only", OUTPUT_CLIPBOARD)
        self.output.setCurrentIndex(max(0, self.output.findData(settings.output)))
        out.addRow("When I press Enter:", self.output)
        self.title = QLineEdit(bs.window_title)
        out.addRow("BibleShow window title contains:", self.title)
        self.format = QComboBox()
        self.format.setEditable(True)
        for label, template in FORMAT_PRESETS.items():
            self.format.addItem(label, template)
        idx = self.format.findData(bs.reference_format)
        if idx >= 0:
            self.format.setCurrentIndex(idx)
        else:
            self.format.setEditText(bs.reference_format)
        out.addRow("Reference format typed into BibleShow:", self.format)
        self.show_after = QCheckBox("Put the verse on screen straight away (otherwise only load it)")
        self.show_after.setChecked(bs.show_after_view)
        out.addRow(self.show_after)
        self.return_focus = QCheckBox("Return keyboard focus to Smart Bible after sending")
        self.return_focus.setChecked(bs.return_focus)
        out.addRow(self.return_focus)
        self.delay = QSpinBox()
        self.delay.setRange(10, 1000)
        self.delay.setSuffix(" ms")
        self.delay.setValue(bs.step_delay_ms)
        out.addRow("Pause between keystrokes:", self.delay)
        layout.addWidget(out_box)

        keys_box = QGroupBox("BibleShow keys (advanced, pywinauto syntax: ^=Ctrl, +=Shift)")
        keys = QFormLayout(keys_box)
        self.key_edits = {}
        for name, label in (
            ("focus_keys", "Focus reference box"),
            ("view_keys", "View typed reference"),
            ("show_keys", "Show on screen"),
            ("hide_keys", "Hide"),
            ("next_keys", "Next verse"),
            ("prev_keys", "Previous verse"),
        ):
            edit = QLineEdit(getattr(bs, name))
            self.key_edits[name] = edit
            keys.addRow(label + ":", edit)
        layout.addWidget(keys_box)

        ai_box = QGroupBox("Online AI search (used when internet is available)")
        ai = QFormLayout(ai_box)
        self.ai_enabled = QCheckBox("Ask Claude for help with fuzzy queries")
        self.ai_enabled.setChecked(settings.ai_enabled)
        ai.addRow(self.ai_enabled)
        self.api_key = QLineEdit(settings.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-ant-...  (from console.anthropic.com)")
        ai.addRow("Anthropic API key:", self.api_key)
        self.model = QLineEdit(settings.ai_model)
        ai.addRow("Model:", self.model)
        layout.addWidget(ai_box)

        misc_box = QGroupBox("Display")
        misc = QFormLayout(misc_box)
        self.font_size = QSpinBox()
        self.font_size.setRange(9, 28)
        self.font_size.setValue(settings.font_size)
        misc.addRow("Font size:", self.font_size)
        folder = QLabel(f"Add your own licensed translations (CSV, Zefania XML or JSON) to:<br><b>{html.escape(str(user_bible_dir()))}</b><br>then restart Smart Bible.")
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        folder.setWordWrap(True)
        misc.addRow(folder)
        layout.addWidget(misc_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.test_button = buttons.addButton("Test with John 3:16", QDialogButtonBox.ActionRole)
        self.test_button.clicked.connect(self._test)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _template(self) -> str:
        idx = self.format.currentIndex()
        if idx >= 0 and self.format.currentText() == self.format.itemText(idx):
            return self.format.itemData(idx)
        return self.format.currentText()

    def apply(self) -> Settings:
        s = self.settings
        s.output = self.output.currentData()
        s.ai_enabled = self.ai_enabled.isChecked()
        s.api_key = self.api_key.text().strip()
        s.ai_model = self.model.text().strip()
        s.font_size = self.font_size.value()
        bs = s.bibleshow
        bs.window_title = self.title.text().strip() or "BibleShow"
        bs.reference_format = self._template()
        bs.show_after_view = self.show_after.isChecked()
        bs.return_focus = self.return_focus.isChecked()
        bs.step_delay_ms = self.delay.value()
        for name, edit in self.key_edits.items():
            setattr(bs, name, edit.text())
        return s

    def _test(self) -> None:
        settings = self.apply()
        ref = Reference(43, 3, 16, 3, 16)
        try:
            typed = BibleShowDriver(settings.bibleshow).send_reference(ref)
        except BibleShowError as exc:
            QMessageBox.warning(self, "BibleShow", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(self, "BibleShow", f"Could not send keys: {exc}")
            return
        self.activateWindow()
        QMessageBox.information(
            self,
            "BibleShow",
            f"Typed “{typed}” into BibleShow.\n\nIf BibleShow did not show John 3:16, try another reference format.",
        )


# ---------------------------------------------------------------- main window


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.engine: SearchEngine | None = None
        self.ai: AIResolver | None = None
        self.driver = BibleShowDriver(settings.bibleshow)
        self.pool = QThreadPool.globalInstance()
        self._query_token = 0
        self._results: list[Result] = []
        self._live_ref: Reference | None = None
        self._ai_status = ""
        self._tasks: set[Task] = set()

        self.setWindowTitle(f"Smart Bible {__version__}")
        self.resize(1100, 680)
        self._build_ui()
        self._configure_ai()
        self._apply_font()

        self.search_timer = QTimer(self, singleShot=True, interval=SEARCH_DELAY_MS, timeout=self._run_search)
        self.ai_timer = QTimer(self, singleShot=True, interval=AI_DELAY_MS, timeout=self._run_ai)
        self.status_timer = QTimer(self, interval=5000, timeout=self._refresh_status)
        self.status_timer.start()

        self._set_status("Loading Bibles…")
        task = Task(0, build_engine)
        task.signals.done.connect(self._engine_ready)
        task.signals.failed.connect(lambda _t, msg: QMessageBox.critical(self, "Smart Bible", msg))
        self._start(task)

    def _start(self, task: Task) -> None:
        """Keep a reference until the task reports back, then let it go."""
        self._tasks.add(task)
        task.setAutoDelete(False)
        task.signals.done.connect(lambda *_: self._tasks.discard(task))
        task.signals.failed.connect(lambda *_: self._tasks.discard(task))
        self.pool.start(task)

    # ------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Type a reference (jn 3 16), a quote, or what the preacher is talking about…"
        )
        self.search.setClearButtonEnabled(True)
        self.search.textEdited.connect(self._on_text)
        self.search.installEventFilter(self)
        top.addWidget(self.search, 1)
        self.translation = QComboBox()
        self.translation.setToolTip("Translation shown in the preview")
        self.translation.currentIndexChanged.connect(self._on_translation)
        top.addWidget(self.translation)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        layout.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.results = QListWidget()
        self.results.setItemDelegate(ResultDelegate(self.results))
        self.results.setWordWrap(True)
        self.results.setUniformItemSizes(False)
        self.results.currentRowChanged.connect(self._on_select)
        self.results.itemDoubleClicked.connect(lambda _i: self.send_current())
        split.addWidget(self.results)
        self.preview = QTextBrowser()
        self.preview.setOpenLinks(False)
        split.addWidget(self.preview)
        split.setSizes([480, 620])
        layout.addWidget(split, 1)

        buttons = QHBoxLayout()

        def button(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            buttons.addWidget(b)
            return b

        self.show_btn = button("Show  (Enter)", "Send the selected verse to BibleShow and show it", self.send_current)
        button("Load only  (Shift+Enter)", "Load in BibleShow without showing", lambda: self.send_current(go_live=False))
        button("▲ Prev verse  (Ctrl+↑)", "BibleShow previous verse", lambda: self._hotkey("prev"))
        button("▼ Next verse  (Ctrl+↓)", "BibleShow next verse", lambda: self._hotkey("next"))
        button("Hide  (F8)", "Hide the verse in BibleShow", lambda: self._hotkey("hide"))
        button("Copy reference", "Copy reference to clipboard", self.copy_current)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.setCentralWidget(root)
        self.ai_label = QLabel()
        self.bs_label = QLabel()
        self.statusBar().addPermanentWidget(self.ai_label)
        self.statusBar().addPermanentWidget(self.bs_label)

        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self._hotkey("next"))
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self._hotkey("prev"))
        QShortcut(QKeySequence("F8"), self, activated=lambda: self._hotkey("hide"))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F2"), self, activated=self._focus_search)

    def _apply_font(self) -> None:
        font = QApplication.font()
        font.setPointSize(self.settings.font_size)
        self.results.setFont(font)
        self.preview.setFont(font)
        big = QFont(font)
        big.setPointSize(self.settings.font_size + 4)
        self.search.setFont(big)
        self.search.setMinimumHeight(int(big.pointSize() * 2.6))

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # ------------------------------------------------------------ status
    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def _refresh_status(self) -> None:
        if self.settings.output == OUTPUT_CLIPBOARD:
            self.bs_label.setText("Output: clipboard")
        elif self.driver.is_running():
            self.bs_label.setText("BibleShow: <span style='color:#2a2'>●</span> found")
        else:
            self.bs_label.setText("BibleShow: <span style='color:#c33'>●</span> not running")
        if not self.settings.ai_enabled:
            self.ai_label.setText("AI: off")
        elif self.ai is None or not self.ai.configured:
            self.ai_label.setText("AI: no API key (offline search only)")
        elif self.ai.online:
            self.ai_label.setText("AI: <span style='color:#2a2'>●</span> ready" + (f" — {self._ai_status}" if self._ai_status else ""))
        else:
            self.ai_label.setText("AI: <span style='color:#c80'>●</span> offline — using offline search")

    def _configure_ai(self) -> None:
        s = self.settings
        self.ai = AIResolver(s.api_key, s.ai_model) if s.ai_enabled and s.api_key else None

    # ------------------------------------------------------------ engine
    def _engine_ready(self, _token, engine: SearchEngine) -> None:
        self.engine = engine
        self.translation.blockSignals(True)
        for bible_id, bible in engine.library.bibles.items():
            self.translation.addItem(f"{bible_id}", bible_id)
            self.translation.setItemData(self.translation.count() - 1, bible.name, Qt.ToolTipRole)
        idx = self.translation.findData(self.settings.translation)
        self.translation.setCurrentIndex(max(0, idx))
        self.translation.blockSignals(False)
        msg = f"Ready — {len(engine.library.bibles)} translations loaded."
        if engine.library.errors:
            msg += "  Could not load: " + "; ".join(engine.library.errors)
        self._set_status(msg)
        self._refresh_status()
        threading.Thread(target=engine.warm_up, daemon=True).start()
        if engine.semantic is not None and not engine.semantic.ready:
            self._build_semantic_index()
        if self.search.text().strip():
            self._run_search()

    def _build_semantic_index(self) -> None:
        engine = self.engine
        sem = engine.semantic
        bible = engine.library.get("BSB") or engine.library.any()
        if not sem.model_available():
            self._set_status(
                "Ready (meaning-based search unavailable: model files missing; word search still works)."
            )
            return
        self._set_status("Preparing meaning-based search (one-time, a few minutes)…")
        task = Task(0, lambda: sem.build(bible, progress=task.signals.progress.emit))
        task.signals.progress.connect(
            lambda done, total: self._set_status(f"Preparing meaning-based search… {done * 100 // total}%")
        )
        task.signals.done.connect(lambda *_: self._set_status("Meaning-based search ready."))
        task.signals.failed.connect(lambda _t, msg: self._set_status(f"Meaning-based search unavailable: {msg}"))
        self._start(task)

    # ------------------------------------------------------------ searching
    def _on_text(self, _text: str) -> None:
        self._query_token += 1
        self.search_timer.start()
        self.ai_timer.stop()
        if self.ai is not None:
            self.ai_timer.start()

    def _run_search(self) -> None:
        if self.engine is None:
            return
        query = self.search.text()
        self._results = self.engine.search(query)
        self._fill_results()

    def _run_ai(self) -> None:
        query = self.search.text().strip()
        if self.engine is None or self.ai is None or len(query) < 4:
            return
        if self._results and "reference" in self._results[0].sources:
            return  # typed an exact reference; no need to ask
        token = self._query_token
        self._ai_status = "thinking…"
        self._refresh_status()
        task = Task(token, self.ai.resolve, query)
        task.signals.done.connect(self._ai_done)
        task.signals.failed.connect(self._ai_failed)
        self._start(task)

    def _ai_done(self, token, suggestions) -> None:
        self._ai_status = ""
        self._refresh_status()
        if token != self._query_token or self.engine is None:
            return  # the operator has typed something else since
        selected = self._selected_result()
        self._results = self.engine.merge_ai(self._results, [(s.ref, s.why) for s in suggestions])
        self._fill_results(keep=selected)

    def _ai_failed(self, token, message: str) -> None:
        self._ai_status = "" if token != self._query_token else message
        self._refresh_status()

    def _fill_results(self, keep: Result | None = None) -> None:
        self.results.blockSignals(True)
        self.results.clear()
        bible_id = self.translation.currentData()
        keep_row = 0
        for row, r in enumerate(self._results):
            rows = self.engine.passage_text(r.ref, bible_id)
            snippet = " ".join(t for _, _, t in rows)[:220]
            tags = ", ".join(SOURCE_LABELS[s] for s in sorted(r.sources) if s in SOURCE_LABELS)
            star = " ✨" if "ai" in r.sources else ""
            note = f" <i>“{html.escape(r.note)}”</i>" if r.note and ("famous" in r.sources or "ai" in r.sources) else ""
            item = QListWidgetItem()
            item.setData(
                Qt.UserRole + 1,
                f"<b>{html.escape(r.ref.display())}</b>{star} <span style='color:gray;font-size:small'>{tags}</span>{note}"
                f"<br>{html.escape(snippet)}",
            )
            self.results.addItem(item)
            if keep is not None and r.key == keep.key:
                keep_row = row
        self.results.blockSignals(False)
        if self._results:
            self.results.setCurrentRow(keep_row)
            self._on_select(keep_row)
        else:
            self.preview.clear()

    def _selected_result(self) -> Result | None:
        row = self.results.currentRow()
        return self._results[row] if 0 <= row < len(self._results) else None

    def _on_select(self, _row: int) -> None:
        r = self._selected_result()
        if r is None or self.engine is None:
            return
        bible_id = self.translation.currentData()
        rows = self.engine.passage_text(r.ref, bible_id)
        body = "".join(
            f"<p><sup style='color:gray'>{(str(c) + ':') if r.ref.end_chapter not in (None, r.ref.chapter) else ''}{v}</sup> {html.escape(t)}</p>"
            for c, v, t in rows
        )
        size = self.settings.font_size + 6
        self.preview.setHtml(
            f"<h2>{html.escape(r.ref.display())} <span style='color:gray;font-size:small'>{html.escape(bible_id or '')}</span></h2>"
            f"<div style='font-size:{size}pt'>{body}</div>"
        )

    def _on_translation(self, _idx: int) -> None:
        self.settings.translation = self.translation.currentData()
        self.settings.save()
        if self._results:
            self._fill_results(keep=self._selected_result())

    # ------------------------------------------------------------ keyboard
    def eventFilter(self, obj, event) -> bool:
        if obj is self.search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up) and event.modifiers() & Qt.ControlModifier:
                self._hotkey("next" if key == Qt.Key_Down else "prev")
                return True
            if key in (Qt.Key_Down, Qt.Key_Up, Qt.Key_PageDown, Qt.Key_PageUp):
                step = {Qt.Key_Down: 1, Qt.Key_Up: -1, Qt.Key_PageDown: 5, Qt.Key_PageUp: -5}[key]
                if self._results:
                    row = min(max(0, self.results.currentRow() + step), len(self._results) - 1)
                    self.results.setCurrentRow(row)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.search_timer.isActive():  # typed fast and hit Enter: search first
                    self.search_timer.stop()
                    self._run_search()
                self.send_current(go_live=False if event.modifiers() & Qt.ShiftModifier else None)
                return True
            if key == Qt.Key_Escape:
                self.search.clear()
                self._results = []
                self._fill_results()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ output
    def send_current(self, go_live: bool | None = None) -> None:
        r = self._selected_result()
        if r is None:
            return
        if self.settings.output == OUTPUT_CLIPBOARD:
            self.copy_current()
            return
        try:
            typed = self.driver.send_reference(r.ref, go_live=go_live)
        except BibleShowError as exc:
            self._set_status(str(exc))
            QApplication.clipboard().setText(r.ref.display())
            return
        except Exception as exc:
            self._set_status(f"Could not control BibleShow: {exc}")
            return
        finally:
            try:
                self.driver.refocus(int(self.winId()))
            except Exception:
                self.activateWindow()
            self._focus_search()
        self._live_ref = r.ref
        extra = "  (range: use Next verse (Ctrl+↓) to step through)" if r.ref.is_range else ""
        self._set_status(f"Sent to BibleShow: {typed}{extra}")

    def copy_current(self) -> None:
        r = self._selected_result()
        if r is None:
            return
        QApplication.clipboard().setText(r.ref.display())
        self._set_status(f"Copied {r.ref.display()}")

    def _hotkey(self, which: str) -> None:
        if self.settings.output == OUTPUT_CLIPBOARD:
            return
        try:
            self.driver.hotkey(which)
            self._set_status({"next": "Next verse", "prev": "Previous verse", "hide": "Hidden", "show": "Shown"}[which])
        except Exception as exc:
            self._set_status(f"Could not control BibleShow: {exc}")

    # ------------------------------------------------------------ settings
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings = dialog.apply()
            self.settings.save()
            self.driver = BibleShowDriver(self.settings.bibleshow)
            self._configure_ai()
            self._apply_font()
            self._refresh_status()
            if self._results:
                self._fill_results(keep=self._selected_result())
        else:
            self.settings = Settings.load()  # discard edits made by "Test"
            self.driver = BibleShowDriver(self.settings.bibleshow)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Smart Bible")
    window = MainWindow(Settings.load())
    window.show()
    window.search.setFocus()
    return app.exec()
