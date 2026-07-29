import re
import frontmatter
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QPlainTextEdit, QFrame, QCompleter, QMenu, QDialog, QListWidget, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QRect, QSize, QStringListModel
from PyQt6.QtGui import QFont, QColor, QPainter, QTextFormat, QKeySequence, QFontMetrics, QShortcut, QTextCursor


class UrlSelectionDialog(QDialog):
    """
    Dialog displaying detected web URLs from note body text when multiple URLs exist.
    Allows user to select which URL to add to the YAML frontmatter.
    """
    def __init__(self, urls: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 Select URL for YAML Property")
        self.resize(550, 300)
        self.selected_url = ""

        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #cccccc;
                font-size: 12px;
            }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 8px;
            }
            QListWidget::item:selected {
                background-color: #0e639c;
                color: #ffffff;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Multiple URLs detected in note text. Select which URL to set as YAML url:</b>"))

        self.list_widget = QListWidget()
        for u in urls:
            self.list_widget.addItem(u)
        self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #3c3c3c;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("✅ Set Selected URL")
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        layout.addLayout(btn_box)

    def _on_ok(self):
        curr = self.list_widget.currentItem()
        if curr:
            self.selected_url = curr.text()
            self.accept()


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
                    font-family: Consolas, monospace;
                    font-size: 12px;
                }
            """)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

    def set_tags_list(self, tags: list):
        formatted_tags = [f"#{t}" if not t.startswith("#") else t for t in tags]
        model = QStringListModel(formatted_tags, self.completer)
        self.completer.setModel(model)

    def line_number_area_width(self):
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        space = 10 + self.fontMetrics().horizontalAdvance('9') * max(digits, 3)
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
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        painter.setPen(QColor("#858585"))
        font = self.font()
        font.setPointSize(max(8, font.pointSize() - 2))
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0, top, self.line_number_area.width() - 5, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _text_under_cursor(self):
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        text = tc.selectedText()
        tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(text) + 1)
        sel = tc.selectedText()
        if sel.startswith("#"):
            return sel
        return text

    def _insert_completion(self, completion):
        tc = self.textCursor()
        extra = len(completion) - len(self._text_under_cursor())
        tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(self._text_under_cursor()))
        tc.insertText(completion)
        self.setTextCursor(tc)

    def keyPressEvent(self, event):
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.ignore()
                return

        if event.key() == Qt.Key.Key_Tab:
            self.insertPlainText("    ")
            event.accept()
            return

        super().keyPressEvent(event)

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
        toolbar.setSpacing(8)

        self.lbl_title = QLabel("Editing Note: None")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #007acc; font-size: 13px;")

        # "Read From..." Dropdown Button
        self.btn_read_from = QPushButton("📖 Read From... ▼")
        self.btn_read_from.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #383838; }
        """)

        read_menu = QMenu(self)
        read_menu.setStyleSheet("""
            QMenu {
                background-color: #252526;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                padding: 4px;
            }
            QMenu::item {
                padding: 5px 20px 5px 12px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #04395e;
                color: #ffffff;
            }
        """)

        act_tags = read_menu.addAction("🏷️ Read Tags (Extract #tags to YAML)")
        act_tags.triggered.connect(self._read_tags_from_body)

        act_url = read_menu.addAction("🌐 Read URL (Extract Body URLs to YAML)")
        act_url.triggered.connect(self._read_url_from_body)

        self.btn_read_from.setMenu(read_menu)

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
        toolbar.addWidget(self.btn_read_from)
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

    def _read_tags_from_body(self):
        content = self.editor.toPlainText()
        if not content.strip():
            return

        # Extract all #tags from body
        raw_body_tags = re.findall(r'(?:^|\s)#([a-zA-Z0-9_\-/\u00C0-\u024F]+)', content)
        body_tags = set(t.strip() for t in raw_body_tags if t.strip())

        if not body_tags:
            QMessageBox.information(self, "Read Tags", "No #tags found in note body text.")
            return

        try:
            post = frontmatter.loads(content)
            meta = dict(post.metadata)

            existing_yaml_tags = set()
            tags_val = meta.get("tags") or meta.get("tag")
            if isinstance(tags_val, str):
                existing_yaml_tags = set(x.strip() for x in re.split(r"[,,\s]+", tags_val) if x.strip())
            elif isinstance(tags_val, list):
                for x in tags_val:
                    if isinstance(x, str):
                        existing_yaml_tags.update(t.strip() for t in re.split(r"[,,\s]+", x) if t.strip())

            new_tags = body_tags - existing_yaml_tags

            if not new_tags:
                QMessageBox.information(self, "Read Tags", "All body #tags are already present in YAML frontmatter.")
                return

            combined_tags = sorted(list(existing_yaml_tags.union(body_tags)))
            meta["tags"] = combined_tags
            post.metadata = meta

            new_content = frontmatter.dumps(post)
            self.editor.setPlainText(new_content)

            QMessageBox.information(
                self, "Read Tags Success",
                f"Successfully added {len(new_tags)} new tag(s) to YAML frontmatter:\n" + ", ".join([f"#{t}" for t in sorted(list(new_tags))])
            )
        except Exception as e:
            QMessageBox.critical(self, "Read Tags Error", f"Failed to parse or update YAML frontmatter: {e}")

    def _read_url_from_body(self):
        content = self.editor.toPlainText()
        if not content.strip():
            return

        # Extract http/https URLs from content
        urls = re.findall(r'https?://[^\s><"\')]+', content)
        cleaned_urls = []
        for u in urls:
            clean = u.rstrip(".,;:!)")
            if clean and clean not in cleaned_urls:
                cleaned_urls.append(clean)

        if not cleaned_urls:
            QMessageBox.information(self, "Read URL", "No web URLs found in note body text.")
            return

        target_url = ""
        if len(cleaned_urls) == 1:
            target_url = cleaned_urls[0]
        else:
            dlg = UrlSelectionDialog(cleaned_urls, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_url:
                target_url = dlg.selected_url
            else:
                return

        if not target_url:
            return

        try:
            post = frontmatter.loads(content)
            meta = dict(post.metadata)
            meta["url"] = target_url
            post.metadata = meta

            new_content = frontmatter.dumps(post)
            self.editor.setPlainText(new_content)

            QMessageBox.information(self, "Read URL Success", f"Updated YAML url property to:\n{target_url}")
        except Exception as e:
            QMessageBox.critical(self, "Read URL Error", f"Failed to update YAML url property: {e}")

    def _on_save(self):
        if not self.current_rel_path:
            return
        content = self.editor.toPlainText()
        self.save_requested.emit(self.current_rel_path, content)

    def _on_cancel(self):
        self.cancel_requested.emit()
