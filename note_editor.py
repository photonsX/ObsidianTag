import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QPlainTextEdit, QFrame, QCompleter
)
from PyQt6.QtCore import pyqtSignal, Qt, QRect, QSize, QStringListModel
from PyQt6.QtGui import QFont, QColor, QPainter, QTextFormat, QKeySequence, QFontMetrics, QShortcut, QTextCursor

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.lineNumberAreaPaintEvent(event)


class MarkdownCodeEditor(QPlainTextEdit):
    def __init__(self, parent=None, font_size=13):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)

        font = QFont("Consolas", font_size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
        """)

        # Completer Setup for #tag Autocomplete
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insert_completion)

        # Popup styling matching Obsidian dark theme
        if self.completer.popup():
            self.completer.popup().setStyleSheet("""
                QAbstractItemView {
                    background-color: #252526;
                    color: #d4d4d4;
                    border: 1px solid #007acc;
                    selection-background-color: #04395e;
                    selection-color: #ffffff;
                    padding: 4px;
                    font-family: Consolas;
                    font-size: 13px;
                }
            """)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

    def set_tags_list(self, tags: list):
        formatted = [f"#{t.lstrip('#')}" for t in tags if t]
        model = QStringListModel(formatted, self.completer)
        self.completer.setModel(model)

    def _text_under_cursor(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        text = cursor.selectedText()
        
        # Look back for # character
        block_text = self.textCursor().block().text()
        pos = self.textCursor().positionInBlock()
        
        match = re.search(r"#([a-zA-Z0-9_\-/]*)$", block_text[:pos])
        if match:
            return f"#{match.group(1)}"
        return text

    def _insert_completion(self, completion: str):
        cursor = self.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()

        match = re.search(r"#([a-zA-Z0-9_\-/]*)$", block_text[:pos])
        if match:
            start_pos = match.start()
            # Move cursor to start of tag prefix
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, pos - start_pos)
            cursor.insertText(completion + " ")
            self.setTextCursor(cursor)

    def line_number_area_width(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

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
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#252526"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#858585"))
                painter.drawText(0, top, self.line_number_area.width() - 5, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def keyPressEvent(self, event):
        # Handle active completion popup
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.ignore()
                return

        # Insert 4 spaces on Tab key instead of changing focus
        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText("    ")
            event.accept()
            return

        super().keyPressEvent(event)

        # Trigger tag autocomplete on #
        completion_prefix = self._text_under_cursor()
        if completion_prefix.startswith("#"):
            if completion_prefix != self.completer.completionPrefix():
                self.completer.setCompletionPrefix(completion_prefix)
                self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))

            cr = self.cursorRect()
            cr.setWidth(self.completer.popup().sizeHintForColumn(0) + self.completer.popup().verticalScrollBar().sizeHint().width() + 20)
            self.completer.complete(cr)
        else:
            self.completer.popup().hide()


class NoteEditorPanel(QWidget):
    save_requested = pyqtSignal(str, str)
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None, font_size=13):
        super().__init__(parent)
        self.current_rel_path = ""
        self.setMinimumHeight(300)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel("Editing Note: None")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #007acc; font-size: 13px;")

        self.btn_save = QPushButton("💾 Save (Ctrl+S)")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 5px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)
        self.btn_save.clicked.connect(self._on_save)

        self.btn_cancel = QPushButton("✖ Cancel (Esc)")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #cccccc;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
            }
            QPushButton:hover { background-color: #505050; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)

        toolbar.addWidget(self.lbl_title, stretch=1)
        toolbar.addWidget(self.btn_save)
        toolbar.addWidget(self.btn_cancel)

        main_layout.addLayout(toolbar)

        # Monospace Text Editor
        self.editor = MarkdownCodeEditor(font_size=font_size)
        main_layout.addWidget(self.editor, stretch=1)

        # Shortcuts
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._on_save)

        cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        cancel_shortcut.activated.connect(self._on_cancel)

    def load_note(self, rel_path: str, content: str, available_tags: list = None):
        self.current_rel_path = rel_path
        self.lbl_title.setText(f"📄 Editing Note: {rel_path}")
        if available_tags:
            self.editor.set_tags_list(available_tags)
        self.editor.setPlainText(content)
        self.editor.setFocus()

    def _on_save(self):
        if not self.current_rel_path:
            return
        content = self.editor.toPlainText()
        self.save_requested.emit(self.current_rel_path, content)

    def _on_cancel(self):
        self.cancel_requested.emit()
