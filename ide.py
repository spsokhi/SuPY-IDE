import sys
import re
import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QFileDialog, QPlainTextEdit, QCompleter, QLabel
)
from PyQt5.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter, QFont, QPainter, QTextCursor
from PyQt5.QtCore import Qt, QRect
import io

# Define the syntax highlighter class for Python
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document, editor):
        super().__init__(document)
        self.editor = editor

        # Set highlighting rules for Python syntax
        self.highlighting_rules = []

        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#87CEEB"))  # Sky blue
        keyword_format.setFontWeight(QFont.Bold)
        keywords = [
            '\\bFalse\\b', '\\bTrue\\b', '\\bNone\\b', '\\band\\b', '\\bas\\b', '\\bassert\\b', '\\basync\\b',
            '\\bawait\\b', '\\bbreak\\b', '\\bclass\\b', '\\bcontinue\\b', '\\bdef\\b', '\\bdel\\b', '\\belif\\b',
            '\\belse\\b', '\\bexcept\\b', '\\bfinally\\b', '\\bfor\\b', '\\bfrom\\b', '\\bglobal\\b', '\\bif\\b',
            '\\bimport\\b', '\\bin\\b', '\\bis\\b', '\\blambda\\b', '\\bnonlocal\\b', '\\bnot\\b', '\\bor\\b',
            '\\bpass\\b', '\\braise\\b', '\\breturn\\b', '\\btry\\b', '\\bwhile\\b', '\\bwith\\b', '\\byield\\b'
        ]
        for word in keywords:
            pattern = re.compile(word)
            self.highlighting_rules.append((pattern, keyword_format))

        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))  # Green
        pattern = re.compile('#[^\n]*')
        self.highlighting_rules.append((pattern, comment_format))

        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))  # Orange
        pattern = re.compile(r'\".*\"|\'.*\'')
        self.highlighting_rules.append((pattern, string_format))

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # Light green
        pattern = re.compile(r'\b\d+\b')
        self.highlighting_rules.append((pattern, number_format))

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, format)

        # Clear previous error highlights
        self.clear_error_highlights()

    def clear_error_highlights(self):
        self.editor.setExtraSelections([])

    def highlight_error_line(self, line_number):
        extra_selections = []

        selection = QTextEdit.ExtraSelection()
        error_line_color = QColor("#FF6347").lighter(120)  # Tomato color, lighter

        selection.format.setBackground(error_line_color)
        selection.cursor = self.editor.textCursor()
        selection.cursor.movePosition(QTextCursor.Start)
        for _ in range(line_number):
            selection.cursor.movePosition(QTextCursor.Down)

        selection.cursor.clearSelection()
        extra_selections.append(selection)
        self.editor.setExtraSelections(extra_selections)

# Line number area
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.code_editor.lineNumberAreaPaintEvent(event)

# Code editor with line numbers and autocompletion
class CodeEditor(QPlainTextEdit):
    def __init__(self, current_theme):
        super().__init__()
        self.current_theme = current_theme  # Pass current theme from SuPYIDE class

        self.lineNumberArea = LineNumberArea(self)

        # Autocompletion setup
        self.completer = None
        self.setCompleter(self.createCompleter())

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def setCompleter(self, completer):
        if completer:
            completer.setWidget(self)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer = completer

    def createCompleter(self):
        keywords = [
            "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue", "def", 
            "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", 
            "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield", 
            "print", "len", "range", "input", "int", "float", "str", "list", "dict", "set", "tuple", "open", "close"
        ]
        completer = QCompleter(keywords)
        return completer

    def lineNumberAreaWidth(self):
        digits = len(str(self.blockCount()))
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), Qt.lightGray)

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(Qt.black)
                painter.drawText(0, top, self.lineNumberArea.width(), self.fontMetrics().height(),
                                 Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()

            # Adjust line highlight color based on the current theme
            lineColor = QColor(Qt.yellow).lighter(160)
            if self.current_theme == 'dark':
                lineColor = QColor(Qt.blue).lighter(140)

            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)

    def keyPressEvent(self, event):
        if self.completer and self.completer.popup().isVisible():
            if event.key() == Qt.Key_Tab:
                event.accept()
                self.insertCompletion(self.completer.currentCompletion())
                return
            elif event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape):
                self.completer.popup().hide()
                return

        super().keyPressEvent(event)

        completion_prefix = self.textUnderCursor()
        if len(completion_prefix) > 1:
            self.completer.setCompletionPrefix(completion_prefix)
            self.completer.complete()

    def insertCompletion(self, completion):
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def textUnderCursor(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.WordUnderCursor)
        return cursor.selectedText()

class SuPYIDE(QWidget):
    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):
        # Set window properties with new name
        self.setWindowTitle('SuPY-IDE')
        self.setGeometry(100, 100, 1000, 700)

        # Create a layout for buttons and the text editor
        main_layout = QVBoxLayout()

        # Horizontal layout for buttons
        button_layout = QHBoxLayout()

        # Text editor for writing code (with line numbers)
        self.current_theme = 'light'  # Set the default theme to light
        self.text_editor = CodeEditor(self.current_theme)
        self.text_editor.setPlaceholderText("Write your Python code here...")
        main_layout.addWidget(self.text_editor)

        # Apply syntax highlighting
        self.highlighter = PythonHighlighter(self.text_editor.document(), self.text_editor)

        # Buttons with styling
        self.run_button = QPushButton('Run Code', self)
        self.clear_button = QPushButton('Clear Output', self)
        self.save_button = QPushButton('Save Code', self)
        self.load_button = QPushButton('Load Code', self)

        # Timer and theme toggle
        self.execution_time_label = QLabel("Execution time: N/A", self)
        self.theme_toggle_button = QPushButton('Toggle Theme (Light/Dark)', self)

        # Add buttons to the horizontal layout
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.theme_toggle_button)

        # Add the button layout and execution time label to the main layout
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.execution_time_label)

        # Output area for results
        self.output_area = QTextEdit(self)
        self.output_area.setReadOnly(True)
        self.output_area.setPlaceholderText("Output will be displayed here...")
        main_layout.addWidget(self.output_area)

        # Footer
        footer_label = QLabel("Made with ❤️ by Sukhpreet Singh", self)
        footer_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(footer_label)

        # Set layout for the window
        self.setLayout(main_layout)

        # Connect buttons to their functions
        self.run_button.clicked.connect(self.run_code)
        self.clear_button.clicked.connect(self.clear_output)
        self.save_button.clicked.connect(self.save_code)
        self.load_button.clicked.connect(self.load_code)
        self.theme_toggle_button.clicked.connect(self.toggle_theme)

    def run_code(self):
        code = self.text_editor.toPlainText()

        # Start timer
        start_time = time.time()

        # Redirect stdout to capture print statements
        old_stdout = sys.stdout
        sys.stdout = output_buffer = io.StringIO()

        try:
            # Clear error highlights
            self.highlighter.clear_error_highlights()

            # Execute the code
            exec_globals = {}
            exec_locals = {}
            exec(code, exec_globals, exec_locals)

            # Capture the output and display it in the output area
            output = output_buffer.getvalue()
            self.output_area.setPlainText(output)
        except Exception as e:
            self.output_area.setPlainText(f"Error: {str(e)}")
            error_line = self.extract_error_line_number(str(e))
            if error_line:
                self.highlighter.highlight_error_line(error_line)
        finally:
            # Reset stdout to default
            sys.stdout = old_stdout

            # Stop timer and display execution time
            execution_time = time.time() - start_time
            self.execution_time_label.setText(f"Execution time: {execution_time:.4f} seconds")

    def extract_error_line_number(self, error_message):
        match = re.search(r'line (\d+)', error_message)
        if match:
            return int(match.group(1))
        return None

    def clear_output(self):
        # Clear the output area and reset the execution time label
        self.output_area.setPlainText("")
        self.execution_time_label.setText("Execution time: N/A")

    def save_code(self):
        # Open a file dialog to save the code
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Code", "", "Python Files (*.py)")
        if file_path:
            with open(file_path, 'w') as file:
                file.write(self.text_editor.toPlainText())

    def load_code(self):
        # Open a file dialog to load code from a file
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Code", "", "Python Files (*.py)")
        if file_path:
            with open(file_path, 'r') as file:
                code = file.read()
                self.text_editor.setPlainText(code)

    def toggle_theme(self):
        if self.current_theme == 'light':
            self.set_dark_theme()
            self.current_theme = 'dark'
        else:
            self.set_light_theme()
            self.current_theme = 'light'

        # Update the theme in the editor
        self.text_editor.current_theme = self.current_theme
        self.text_editor.highlightCurrentLine()

    def set_dark_theme(self):
        self.setStyleSheet("background-color: #2B2B2B; color: #FFFFFF;")
        self.text_editor.setStyleSheet("background-color: #2B2B2B; color: #FFFFFF;")
        self.output_area.setStyleSheet("background-color: #2B2B2B; color: #FFFFFF;")
        self.run_button.setStyleSheet("background-color: #3E3E3E; color: white;")
        self.clear_button.setStyleSheet("background-color: #3E3E3E; color: white;")
        self.save_button.setStyleSheet("background-color: #3E3E3E; color: white;")
        self.load_button.setStyleSheet("background-color: #3E3E3E; color: white;")
        self.theme_toggle_button.setStyleSheet("background-color: #3E3E3E; color: white;")
        self.execution_time_label.setStyleSheet("color: white;")

    def set_light_theme(self):
        self.setStyleSheet("background-color: #FFFFFF; color: #000000;")
        self.text_editor.setStyleSheet("background-color: #FFFFFF; color: #000000;")
        self.output_area.setStyleSheet("background-color: #FFFFFF; color: #000000;")
        self.run_button.setStyleSheet("background-color: #F0F0F0; color: black;")
        self.clear_button.setStyleSheet("background-color: #F0F0F0; color: black;")
        self.save_button.setStyleSheet("background-color: #F0F0F0; color: black;")
        self.load_button.setStyleSheet("background-color: #F0F0F0; color: black;")
        self.theme_toggle_button.setStyleSheet("background-color: #F0F0F0; color: black;")
        self.execution_time_label.setStyleSheet("color: black;")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ide = SuPYIDE()
    ide.show()
    sys.exit(app.exec_())
