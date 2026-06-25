#!/usr/bin/env python3
"""
SuPY-IDE — a lightweight, single-file Python IDE built with PyQt5.

Features
--------
* Syntax highlighting (keywords, builtins, strings incl. triple-quoted,
  numbers, comments, decorators, def/class names, ``self``).
* Smart editor: auto-indentation, tab-to-spaces, bracket/quote auto-closing,
  comment toggling and smart backspace.
* Autocompletion for Python keywords and builtins.
* Code is executed in a **separate process** (via QProcess) so the UI never
  freezes, infinite loops can be stopped, real tracebacks are shown and
  ``input()`` works through the interactive input box.
* Error lines are highlighted from the traceback.
* Find & Replace bar (Ctrl+F / Ctrl+H) with wrap-around search.
* Light / dark themes, editor zoom, line numbers with current-line gutter.
* File handling with modified-state tracking and unsaved-changes prompts.

Made with care by Sukhpreet Singh.
"""

import sys
import os
import re
import time
import shutil
import keyword
import builtins
import tempfile

from PyQt5.QtCore import Qt, QRect, QSize, QProcess
from PyQt5.QtGui import (
    QColor, QTextCharFormat, QSyntaxHighlighter, QFont, QPainter,
    QTextCursor, QTextFormat, QTextDocument, QFontMetricsF, QKeySequence,
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QTextEdit, QPushButton, QFileDialog,
    QPlainTextEdit, QCompleter, QLabel, QMainWindow, QAction, QToolBar,
    QStatusBar, QSplitter, QLineEdit, QMessageBox, QVBoxLayout,
)

# --------------------------------------------------------------------------- #
#  Themes
# --------------------------------------------------------------------------- #

THEMES = {
    "dark": {
        "window": "#1e1f22",
        "editor_bg": "#1e1f22",
        "editor_fg": "#e6e6e6",
        "gutter_bg": "#2b2d30",
        "gutter_fg": "#7a7e85",
        "gutter_fg_current": "#d7dae0",
        "current_line": "#2a2d33",
        "error_line": "#5a2a2a",
        "output_bg": "#181a1b",
        "output_fg": "#d4d4d4",
        "error_text": "#f48771",
        "input_echo": "#6a9955",
        "syntax": {
            "keyword": "#569cd6",
            "builtin": "#4ec9b0",
            "string": "#ce9178",
            "comment": "#6a9955",
            "number": "#b5cea8",
            "decorator": "#dcdcaa",
            "function": "#dcdcaa",
            "class": "#4ec9b0",
            "self": "#9cdcfe",
        },
    },
    "light": {
        "window": "#ffffff",
        "editor_bg": "#ffffff",
        "editor_fg": "#1f1f1f",
        "gutter_bg": "#f0f0f0",
        "gutter_fg": "#9aa0a6",
        "gutter_fg_current": "#1f1f1f",
        "current_line": "#eef3fb",
        "error_line": "#ffd6d6",
        "output_bg": "#fafafa",
        "output_fg": "#1f1f1f",
        "error_text": "#c0392b",
        "input_echo": "#107c10",
        "syntax": {
            "keyword": "#0000ff",
            "builtin": "#267f99",
            "string": "#a31515",
            "comment": "#008000",
            "number": "#098658",
            "decorator": "#795e26",
            "function": "#795e26",
            "class": "#267f99",
            "self": "#001080",
        },
    },
}

# Characters that get auto-closed when typed.
PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
CLOSERS = set(PAIRS.values())


def python_interpreter():
    """Return a usable Python interpreter path, even from a frozen build."""
    if getattr(sys, "frozen", False):
        return shutil.which("python") or shutil.which("python3") or "python"
    return sys.executable


# --------------------------------------------------------------------------- #
#  Syntax highlighter
# --------------------------------------------------------------------------- #

class PythonHighlighter(QSyntaxHighlighter):
    """Regex-based highlighter with proper multi-line (triple-quoted) strings."""

    def __init__(self, document, theme="dark"):
        super().__init__(document)
        self.set_theme(theme)

    def set_theme(self, theme):
        palette = THEMES[theme]["syntax"]
        self.rules = []

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        # Keywords.
        kw_fmt = fmt(palette["keyword"], bold=True)
        for word in keyword.kwlist:
            self.rules.append((re.compile(r"\b" + word + r"\b"), kw_fmt))

        # Builtins.
        names = [b for b in dir(builtins) if not b.startswith("_")]
        self.rules.append(
            (re.compile(r"\b(" + "|".join(names) + r")\b"), fmt(palette["builtin"]))
        )

        # ``self`` / ``cls``.
        self.rules.append((re.compile(r"\b(self|cls)\b"), fmt(palette["self"], italic=True)))

        # def / class names.
        self.rules.append((re.compile(r"(?<=\bdef\s)\w+"), fmt(palette["function"])))
        self.rules.append((re.compile(r"(?<=\bclass\s)\w+"), fmt(palette["class"])))

        # Decorators.
        self.rules.append((re.compile(r"@\w+(?:\.\w+)*"), fmt(palette["decorator"])))

        # Numbers (ints, floats, hex).
        self.rules.append(
            (re.compile(r"\b(0[xX][0-9a-fA-F]+|\d+\.?\d*([eE][+-]?\d+)?)\b"),
             fmt(palette["number"]))
        )

        # Single-line strings (handles escaped quotes).
        self.string_fmt = fmt(palette["string"])
        self.rules.append((re.compile(r"'[^'\\\n]*(\\.[^'\\\n]*)*'"), self.string_fmt))
        self.rules.append((re.compile(r'"[^"\\\n]*(\\.[^"\\\n]*)*"'), self.string_fmt))

        # Comments (applied last so they win over keywords inside them).
        self.rules.append((re.compile(r"#[^\n]*"), fmt(palette["comment"], italic=True)))

        self.tri_single = re.compile(r"'''")
        self.tri_double = re.compile(r'"""')
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, char_fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), char_fmt)

        # Multi-line triple-quoted strings via block states.
        self.setCurrentBlockState(0)
        if not self._match_multiline(text, self.tri_single, 1):
            self._match_multiline(text, self.tri_double, 2)

    def _match_multiline(self, text, delimiter, in_state):
        if self.previousBlockState() == in_state:
            start, add = 0, 0
        else:
            match = delimiter.search(text)
            if not match:
                return False
            start, add = match.start(), match.end() - match.start()

        while start >= 0:
            match = delimiter.search(text, start + add)
            if match:
                length = match.end() - start
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(in_state)
                length = len(text) - start
            self.setFormat(start, length, self.string_fmt)
            nxt = delimiter.search(text, start + length)
            if nxt:
                start, add = nxt.start(), nxt.end() - nxt.start()
            else:
                start = -1
        return self.currentBlockState() == in_state


# --------------------------------------------------------------------------- #
#  Line number gutter
# --------------------------------------------------------------------------- #

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


# --------------------------------------------------------------------------- #
#  Code editor
# --------------------------------------------------------------------------- #

class CodeEditor(QPlainTextEdit):
    """Plain-text editor with line numbers, smart editing and completion."""

    def __init__(self, theme="dark"):
        super().__init__()
        self._palette = THEMES[theme]
        self.error_lines = set()

        self.line_number_area = LineNumberArea(self)

        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setFixedPitch(True)
        font.setPointSize(11)
        self._base_font = font
        self.setFont(font)
        self._apply_tab_width()

        self.completer = None
        self.set_completer(self._build_completer())

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.update_extra_selections)

        self.update_line_number_area_width(0)
        self.update_extra_selections()

    # -- completion -------------------------------------------------------- #

    def _build_completer(self):
        words = sorted(set(keyword.kwlist + [b for b in dir(builtins) if not b.startswith("_")]))
        completer = QCompleter(words)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        return completer

    def set_completer(self, completer):
        if completer:
            completer.setWidget(self)
            completer.activated.connect(self.insert_completion)
        self.completer = completer

    def insert_completion(self, completion):
        cursor = self.textCursor()
        prefix = self.completer.completionPrefix()
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def text_under_cursor(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText()

    # -- theming / font ---------------------------------------------------- #

    def set_theme(self, theme):
        self._palette = THEMES[theme]
        self.update_extra_selections()
        self.line_number_area.update()

    def _apply_tab_width(self):
        metrics = QFontMetricsF(self.font())
        self.setTabStopDistance(4 * metrics.horizontalAdvance(" "))

    def zoom(self, delta):
        if delta > 0:
            self.zoomIn(1)
        elif delta < 0:
            self.zoomOut(1)
        else:  # reset
            self.setFont(self._base_font)
        self._apply_tab_width()
        self.update_line_number_area_width(0)

    # -- gutter ------------------------------------------------------------ #

    def line_number_area_width(self):
        digits = max(2, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self._palette["gutter_bg"]))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current:
                    painter.setPen(QColor(self._palette["gutter_fg_current"]))
                else:
                    painter.setPen(QColor(self._palette["gutter_fg"]))
                painter.drawText(0, top, self.line_number_area.width() - 6,
                                 self.fontMetrics().height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    # -- selections (current line + error lines) --------------------------- #

    def clear_error_lines(self):
        if self.error_lines:
            self.error_lines.clear()
            self.update_extra_selections()

    def set_error_lines(self, lines):
        self.error_lines = {n for n in lines if 1 <= n <= self.blockCount()}
        self.update_extra_selections()

    def update_extra_selections(self):
        selections = []

        for line in self.error_lines:
            block = self.document().findBlockByNumber(line - 1)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(self._palette["error_line"]))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = QTextCursor(block)
            selection.cursor.clearSelection()
            selections.append(selection)

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(self._palette["current_line"]))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)

        self.setExtraSelections(selections)

    # -- smart editing helpers --------------------------------------------- #

    def _char_after(self, cursor):
        text = cursor.block().text()
        pos = cursor.positionInBlock()
        return text[pos] if pos < len(text) else ""

    def _char_before(self, cursor):
        text = cursor.block().text()
        pos = cursor.positionInBlock()
        return text[pos - 1] if pos > 0 else ""

    def _handle_newline(self):
        cursor = self.textCursor()
        line = cursor.block().text()
        indent = re.match(r"\s*", line).group()
        if line[:cursor.positionInBlock()].rstrip().endswith(":"):
            indent += "    "
        cursor.insertText("\n" + indent)
        self.setTextCursor(cursor)

    def _indent_selection(self, dedent=False):
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        first = cursor.blockNumber()
        cursor.setPosition(end)
        last = cursor.blockNumber()
        cursor.beginEditBlock()
        doc = self.document()
        for number in range(first, last + 1):
            block = doc.findBlockByNumber(number)
            line_cursor = QTextCursor(block)
            if dedent:
                text = block.text()
                remove = len(text) - len(text.lstrip(" "))
                remove = min(remove, 4)
                for _ in range(remove):
                    line_cursor.deleteChar()
            else:
                line_cursor.insertText("    ")
        cursor.endEditBlock()

    def _handle_smart_backspace(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        before, after = self._char_before(cursor), self._char_after(cursor)
        if before in PAIRS and PAIRS[before] == after:
            cursor.deleteChar()
            cursor.deletePreviousChar()
            return True
        pos = cursor.positionInBlock()
        prefix = cursor.block().text()[:pos]
        if prefix and not prefix.strip():
            count = pos - 4 * ((pos - 1) // 4)
            for _ in range(count):
                cursor.deletePreviousChar()
            return True
        return False

    def _handle_autoclose(self, text):
        cursor = self.textCursor()
        if text in CLOSERS and self._char_after(cursor) == text:
            cursor.movePosition(QTextCursor.Right)
            self.setTextCursor(cursor)
            return True
        if text in PAIRS:
            if cursor.hasSelection():
                selected = cursor.selectedText()
                cursor.insertText(text + selected + PAIRS[text])
                return True
            if text in ("'", '"') and self._char_before(cursor).isalnum():
                return False
            after = self._char_after(cursor)
            if after == "" or after in CLOSERS or after in " \t,;:":
                cursor.insertText(text + PAIRS[text])
                cursor.movePosition(QTextCursor.Left)
                self.setTextCursor(cursor)
                return True
        return False

    def toggle_comment(self):
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        first = cursor.blockNumber()
        cursor.setPosition(end)
        last = cursor.blockNumber()
        doc = self.document()
        blocks = [doc.findBlockByNumber(n) for n in range(first, last + 1)]
        non_empty = [b for b in blocks if b.text().strip()]
        if not non_empty:
            return
        all_commented = all(b.text().lstrip().startswith("#") for b in non_empty)

        cursor.beginEditBlock()
        for block in blocks:
            text = block.text()
            if not text.strip():
                continue
            line_cursor = QTextCursor(block)
            if all_commented:
                idx = text.find("#")
                line_cursor.setPosition(block.position() + idx)
                line_cursor.deleteChar()
                if idx < len(block.text()) and block.text()[idx] == " ":
                    line_cursor.deleteChar()
            else:
                indent = len(text) - len(text.lstrip())
                line_cursor.setPosition(block.position() + indent)
                line_cursor.insertText("# ")
        cursor.endEditBlock()

    # -- key handling ------------------------------------------------------ #

    def keyPressEvent(self, event):
        popup = self.completer.popup() if self.completer else None
        if popup and popup.isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
                event.accept()
                self.insert_completion(self.completer.currentCompletion())
                popup.hide()
                return
            if event.key() == Qt.Key_Escape:
                popup.hide()
                return

        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._handle_newline()
            return
        if key == Qt.Key_Tab and not self.textCursor().hasSelection():
            self.insertPlainText("    ")
            return
        if key == Qt.Key_Tab:
            self._indent_selection()
            return
        if key == Qt.Key_Backtab:
            self._indent_selection(dedent=True)
            return
        if key == Qt.Key_Backspace and self._handle_smart_backspace():
            return
        if event.text() and self._handle_autoclose(event.text()):
            return

        super().keyPressEvent(event)

        if not self.completer:
            return
        prefix = self.text_under_cursor()
        char = event.text()
        if len(prefix) >= 2 and char and (char.isalnum() or char == "_"):
            if prefix != self.completer.completionPrefix():
                self.completer.setCompletionPrefix(prefix)
                self.completer.popup().setCurrentIndex(
                    self.completer.completionModel().index(0, 0))
            rect = self.cursorRect()
            rect.setWidth(self.completer.popup().sizeHintForColumn(0)
                          + self.completer.popup().verticalScrollBar().sizeHint().width())
            self.completer.complete(rect)
        elif self.completer.popup().isVisible():
            self.completer.popup().hide()


# --------------------------------------------------------------------------- #
#  Find & Replace bar
# --------------------------------------------------------------------------- #

class FindReplaceBar(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self.find_field = QLineEdit()
        self.find_field.setPlaceholderText("Find")
        self.replace_field = QLineEdit()
        self.replace_field.setPlaceholderText("Replace with")

        next_btn = QPushButton("Next")
        prev_btn = QPushButton("Prev")
        replace_btn = QPushButton("Replace")
        all_btn = QPushButton("Replace All")
        close_btn = QPushButton("✕")
        close_btn.setFixedWidth(28)

        for widget in (self.find_field, next_btn, prev_btn,
                       self.replace_field, replace_btn, all_btn, close_btn):
            layout.addWidget(widget)

        self.find_field.returnPressed.connect(self.find_next)
        next_btn.clicked.connect(self.find_next)
        prev_btn.clicked.connect(self.find_prev)
        replace_btn.clicked.connect(self.replace_one)
        all_btn.clicked.connect(self.replace_all)
        close_btn.clicked.connect(self.hide)
        self.hide()

    def open(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            self.find_field.setText(cursor.selectedText())
        self.show()
        self.find_field.setFocus()
        self.find_field.selectAll()

    def _find(self, backward=False):
        text = self.find_field.text()
        if not text:
            return False
        flags = QTextDocument.FindFlags()
        if backward:
            flags |= QTextDocument.FindBackward
        if self.editor.find(text, flags):
            return True
        # Wrap around.
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End if backward else QTextCursor.Start)
        self.editor.setTextCursor(cursor)
        return self.editor.find(text, flags)

    def find_next(self):
        self._find(backward=False)

    def find_prev(self):
        self._find(backward=True)

    def replace_one(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == self.find_field.text():
            cursor.insertText(self.replace_field.text())
        self.find_next()

    def replace_all(self):
        text = self.find_field.text()
        if not text:
            return
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.Start)
        self.editor.setTextCursor(cursor)
        count = 0
        while self.editor.find(text):
            self.editor.textCursor().insertText(self.replace_field.text())
            count += 1
        cursor.endEditBlock()
        self.window().statusBar().showMessage(f"Replaced {count} occurrence(s).", 4000)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.editor.setFocus()
        else:
            super().keyPressEvent(event)


# --------------------------------------------------------------------------- #
#  Main window
# --------------------------------------------------------------------------- #

class SuPYIDE(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_theme = "dark"
        self.current_file = None
        self.process = None
        self._temp_path = None
        self._stderr_buffer = ""
        self._start_time = 0.0
        self.init_ui()
        self.apply_theme(self.current_theme)
        self.update_title()

    # -- UI construction --------------------------------------------------- #

    def init_ui(self):
        self.setGeometry(100, 100, 1100, 760)

        self.editor = CodeEditor(self.current_theme)
        self.editor.setPlaceholderText("Write your Python code here…  (F5 to run)")
        self.highlighter = PythonHighlighter(self.editor.document(), self.current_theme)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._update_position)

        self.find_bar = FindReplaceBar(self.editor)

        self.output_area = QPlainTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText("Program output will appear here…")
        self.output_area.setFont(self.editor.font())

        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Program input (stdin) — type and press Enter while running")
        self.input_line.setEnabled(False)
        self.input_line.returnPressed.connect(self.send_input)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(self.find_bar)
        editor_layout.addWidget(self.editor)

        output_panel = QWidget()
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(2)
        output_layout.addWidget(self.output_area)
        output_layout.addWidget(self.input_line)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(editor_panel)
        splitter.addWidget(output_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 220])
        self.setCentralWidget(splitter)

        self._build_actions()
        self._build_toolbar()
        self._build_menu()
        self._build_statusbar()

    def _build_actions(self):
        def action(text, shortcut=None, handler=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            if handler:
                act.triggered.connect(handler)
            return act

        self.act_new = action("New", "Ctrl+N", self.new_file)
        self.act_open = action("Open…", "Ctrl+O", self.open_file)
        self.act_save = action("Save", "Ctrl+S", self.save_file)
        self.act_save_as = action("Save As…", "Ctrl+Shift+S", self.save_file_as)
        self.act_run = action("Run", "F5", self.run_code)
        self.act_stop = action("Stop", "Shift+F5", self.stop_code)
        self.act_stop.setEnabled(False)
        self.act_clear = action("Clear Output", "Ctrl+L", self.clear_output)
        self.act_find = action("Find / Replace…", "Ctrl+F", self.find_bar.open)
        self.act_replace = action("Replace…", "Ctrl+H", self.find_bar.open)
        self.act_comment = action("Toggle Comment", "Ctrl+/", self.editor.toggle_comment)
        self.act_zoom_in = action("Zoom In", "Ctrl+=", lambda: self.editor.zoom(1))
        self.act_zoom_out = action("Zoom Out", "Ctrl+-", lambda: self.editor.zoom(-1))
        self.act_zoom_reset = action("Reset Zoom", "Ctrl+0", lambda: self.editor.zoom(0))
        self.act_theme = action("Toggle Theme", "Ctrl+T", self.toggle_theme)
        self.act_about = action("About", None, self.show_about)
        self.act_quit = action("Quit", "Ctrl+Q", self.close)

    def _build_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for act in (self.act_new, self.act_open, self.act_save):
            toolbar.addAction(act)
        toolbar.addSeparator()
        toolbar.addAction(self.act_run)
        toolbar.addAction(self.act_stop)
        toolbar.addAction(self.act_clear)
        toolbar.addSeparator()
        toolbar.addAction(self.act_theme)

    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        for act in (self.act_new, self.act_open, self.act_save, self.act_save_as):
            file_menu.addAction(act)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = bar.addMenu("&Edit")
        for act in (self.act_find, self.act_replace, self.act_comment):
            edit_menu.addAction(act)

        run_menu = bar.addMenu("&Run")
        run_menu.addAction(self.act_run)
        run_menu.addAction(self.act_stop)
        run_menu.addAction(self.act_clear)

        view_menu = bar.addMenu("&View")
        for act in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset, self.act_theme):
            view_menu.addAction(act)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)

    def _build_statusbar(self):
        self.setStatusBar(QStatusBar())
        self.position_label = QLabel("Ln 1, Col 1")
        self.exec_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.position_label)
        self.statusBar().addPermanentWidget(self.exec_label)

    # -- title / status helpers ------------------------------------------- #

    def update_title(self):
        name = os.path.basename(self.current_file) if self.current_file else "Untitled"
        star = "*" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{name}{star} — SuPY-IDE")

    def _on_text_changed(self):
        self.editor.clear_error_lines()
        self.update_title()

    def _update_position(self):
        cursor = self.editor.textCursor()
        self.position_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}")

    # -- theming ----------------------------------------------------------- #

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.apply_theme(self.current_theme)

    def apply_theme(self, theme):
        palette = THEMES[theme]
        self.editor.set_theme(theme)
        self.highlighter.set_theme(theme)
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {palette['window']};
                                    color: {palette['editor_fg']}; }}
            QPlainTextEdit {{ background-color: {palette['editor_bg']};
                              color: {palette['editor_fg']};
                              border: none; selection-background-color: #2f6fbf; }}
            QLineEdit {{ background-color: {palette['editor_bg']};
                         color: {palette['editor_fg']};
                         border: 1px solid {palette['gutter_bg']}; padding: 3px; }}
            QPushButton {{ background-color: {palette['gutter_bg']};
                           color: {palette['editor_fg']};
                           border: none; padding: 4px 10px; border-radius: 3px; }}
            QPushButton:hover {{ background-color: #3a6ea5; }}
            QToolBar {{ background-color: {palette['gutter_bg']}; border: none; spacing: 4px; }}
            QMenuBar, QMenu {{ background-color: {palette['gutter_bg']};
                               color: {palette['editor_fg']}; }}
            QMenuBar::item:selected, QMenu::item:selected {{ background-color: #3a6ea5; }}
            QStatusBar {{ background-color: {palette['gutter_bg']};
                          color: {palette['editor_fg']}; }}
        """)
        self.output_area.setStyleSheet(
            f"background-color: {palette['output_bg']}; color: {palette['output_fg']}; border: none;")

    # -- output helpers ---------------------------------------------------- #

    def append_output(self, text, color=None):
        cursor = self.output_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(QColor(color))
        cursor.insertText(text, fmt)
        self.output_area.setTextCursor(cursor)
        self.output_area.ensureCursorVisible()

    def clear_output(self):
        self.output_area.clear()
        self.exec_label.setText("Ready")
        self.editor.clear_error_lines()

    # -- running code ------------------------------------------------------ #

    def run_code(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            return
        code = self.editor.toPlainText()
        if not code.strip():
            self.statusBar().showMessage("Nothing to run.", 3000)
            return

        self.output_area.clear()
        self.editor.clear_error_lines()
        self._cleanup_temp()

        fd, path = tempfile.mkstemp(suffix=".py", prefix="supy_")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(code)
        self._temp_path = path
        self._stderr_buffer = ""

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

        self._start_time = time.time()
        self._set_running(True)
        self.exec_label.setText("Running…")
        self.process.start(python_interpreter(), ["-u", path])

    def _set_running(self, running):
        self.act_run.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.input_line.setEnabled(running)
        if running:
            self.input_line.setFocus()

    def _on_stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        self.append_output(data, self.output_area.palette().text().color().name())

    def _on_stderr(self):
        data = bytes(self.process.readAllStandardError()).decode("utf-8", "replace")
        self._stderr_buffer += data
        self.append_output(data, THEMES[self.current_theme]["error_text"])

    def _on_finished(self, exit_code, _status):
        elapsed = time.time() - self._start_time
        self._highlight_error_line()
        if exit_code == 0:
            self.exec_label.setText(f"Finished in {elapsed:.3f}s")
        else:
            self.exec_label.setText(f"Exited with code {exit_code} ({elapsed:.3f}s)")
        self._set_running(False)
        self._cleanup_temp()
        self.process = None

    def _highlight_error_line(self):
        if not self._temp_path:
            return
        name = os.path.basename(self._temp_path)
        lines = [int(m.group(2))
                 for m in re.finditer(r'File "([^"]+)", line (\d+)', self._stderr_buffer)
                 if os.path.basename(m.group(1)) == name]
        if lines:
            self.editor.set_error_lines([lines[-1]])

    def stop_code(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.append_output("\n[Execution stopped]\n",
                               THEMES[self.current_theme]["error_text"])

    def send_input(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            text = self.input_line.text()
            self.process.write((text + "\n").encode("utf-8"))
            self.append_output(text + "\n", THEMES[self.current_theme]["input_echo"])
            self.input_line.clear()

    def _cleanup_temp(self):
        if self._temp_path and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except OSError:
                pass
        self._temp_path = None

    # -- file handling ----------------------------------------------------- #

    def _maybe_save(self):
        if not self.editor.document().isModified():
            return True
        choice = QMessageBox.question(
            self, "Unsaved changes",
            "You have unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if choice == QMessageBox.Save:
            return self.save_file()
        return choice == QMessageBox.Discard

    def new_file(self):
        if not self._maybe_save():
            return
        self.editor.clear()
        self.current_file = None
        self.editor.document().setModified(False)
        self.update_title()

    def open_file(self):
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Code", "", "Python Files (*.py);;All Files (*)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as handle:
            self.editor.setPlainText(handle.read())
        self.current_file = path
        self.editor.document().setModified(False)
        self.update_title()

    def save_file(self):
        if not self.current_file:
            return self.save_file_as()
        with open(self.current_file, "w", encoding="utf-8") as handle:
            handle.write(self.editor.toPlainText())
        self.editor.document().setModified(False)
        self.update_title()
        self.statusBar().showMessage(f"Saved {self.current_file}", 3000)
        return True

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Code", "", "Python Files (*.py);;All Files (*)")
        if not path:
            return False
        self.current_file = path
        return self.save_file()

    # -- misc -------------------------------------------------------------- #

    def show_about(self):
        QMessageBox.about(
            self, "About SuPY-IDE",
            "<h3>SuPY-IDE</h3>"
            "<p>A lightweight Python IDE built with PyQt5.</p>"
            "<p>Made with care by <b>Sukhpreet Singh</b>.</p>")

    def closeEvent(self, event):
        if not self._maybe_save():
            event.ignore()
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self._cleanup_temp()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SuPY-IDE")
    ide = SuPYIDE()
    ide.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
