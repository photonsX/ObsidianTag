import re
import frontmatter
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QPlainTextEdit, QFrame, QCompleter, QMenu, QDialog, QListWidget, QMessageBox,
    QStackedWidget, QTextBrowser, QCheckBox, QComboBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QRect, QSize, QStringListModel, QTimer
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
    title_renamed = pyqtSignal(str, str)

    def __init__(self, parent=None, font_size=13):
        super().__init__(parent)
        self.current_rel_path = ""
        self.ignore_text_changes = False
        self.countdown_seconds = 5
        self.current_font_size = font_size
        self.setMinimumHeight(300)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        button_style = """
            QPushButton {
                background-color: #2d2d2d;
                color: #cccccc;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #383838; }
            QPushButton:checked {
                background-color: #0e639c;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #252526;
                color: #555555;
                border: 1px solid #333333;
            }
        """

        # Toolbar Row
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)

        # Mode Toggle Buttons (Source vs Markdown Preview)
        self.btn_mode_source = QPushButton("📝 Source")
        self.btn_mode_source.setCheckable(True)
        self.btn_mode_source.setChecked(True)
        self.btn_mode_source.setStyleSheet(button_style)

        self.btn_mode_preview = QPushButton("👁️ Preview")
        self.btn_mode_preview.setCheckable(True)
        self.btn_mode_preview.setChecked(False)
        self.btn_mode_preview.setStyleSheet(button_style)

        self.btn_mode_source.clicked.connect(lambda: self._set_view_mode("source"))
        self.btn_mode_preview.clicked.connect(lambda: self._set_view_mode("preview"))

        # Font / Text Scaling Dropdown
        self.combo_font_size = QComboBox()
        self.combo_font_size.addItems(["10pt", "11pt", "12pt", "13pt", "14pt", "16pt", "18pt", "20pt"])
        self.combo_font_size.setCurrentText(f"{font_size}pt")
        self.combo_font_size.setToolTip("Scale text / font size for preview and editor")
        self.combo_font_size.setStyleSheet("""
            QComboBox {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
            }
            QComboBox:disabled {
                background-color: #252526;
                color: #555555;
                border: 1px solid #333333;
            }
        """)
        self.combo_font_size.currentTextChanged.connect(self._on_font_size_changed)

        # Top Right Fixed Status Area: Auto-Save Controls
        self.chk_autosave = QCheckBox("Auto-Save")
        self.chk_autosave.setChecked(True)
        self.chk_autosave.setStyleSheet("color: #cccccc; font-size: 11px; font-weight: bold;")

        self.lbl_autosave_status = QLabel("No active note")
        self.lbl_autosave_status.setStyleSheet("color: #777777; font-size: 11px;")
        self.lbl_autosave_status.setMinimumWidth(120)
        self.lbl_autosave_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.btn_cancel_autosave = QPushButton("✖ Cancel")
        self.btn_cancel_autosave.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: #ffffff;
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c9302c; }
        """)
        self.btn_cancel_autosave.hide()
        self.btn_cancel_autosave.clicked.connect(self._cancel_autosave_countdown)

        # Timer setup for 5s auto-save countdown
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(1000)
        self.autosave_timer.timeout.connect(self._on_autosave_tick)

        # "Read From..." Dropdown Button
        self.btn_read_from = QPushButton("📖 Read From... ▼")
        self.btn_read_from.setStyleSheet(button_style)

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

        act_author = read_menu.addAction("✍️ Read Author (Extract Body Author to YAML)")
        act_author.triggered.connect(self._read_author_from_body)

        act_date = read_menu.addAction("📅 Capture Created Date (Set created: in YAML)")
        act_date.triggered.connect(self._read_created_date_from_file)

        read_menu.addSeparator()
        act_fix_tags = read_menu.addAction("🛠️ Fix YAML Tags (Kebab-case List Format)")
        act_fix_tags.triggered.connect(self._fix_yaml_tags_in_note)

        self.btn_read_from.setMenu(read_menu)

        self.btn_save = QPushButton("💾 Save (Ctrl+S)")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #252526;
                color: #555555;
                border: 1px solid #333333;
            }
        """)
        self.btn_save.clicked.connect(self._on_save)

        self.btn_cancel = QPushButton("✖ Cancel (Esc)")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #3c3c3c;
                color: #cccccc;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #505050; }
            QPushButton:disabled {
                background-color: #252526;
                color: #555555;
                border: 1px solid #333333;
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)

        # Assemble Toolbar
        toolbar.addWidget(self.btn_mode_source)
        toolbar.addWidget(self.btn_mode_preview)
        toolbar.addWidget(self.combo_font_size)
        toolbar.addSpacing(10)
        toolbar.addWidget(self.chk_autosave)
        toolbar.addWidget(self.lbl_autosave_status)
        toolbar.addWidget(self.btn_cancel_autosave)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_read_from)
        toolbar.addWidget(self.btn_save)
        toolbar.addWidget(self.btn_cancel)

        main_layout.addLayout(toolbar)

        # Editor Stack: Source Code Editor (0) vs Rendered Markdown Preview (1)
        self.editor_stack = QStackedWidget(self)

        self.editor = MarkdownCodeEditor(font_size=font_size)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor_stack.addWidget(self.editor)

        self.preview_browser = QTextBrowser(self)
        self.preview_browser.setOpenExternalLinks(True)
        self._apply_preview_font_size(font_size)
        self.editor_stack.addWidget(self.preview_browser)

        main_layout.addWidget(self.editor_stack, stretch=1)

        # Shortcuts
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self._on_save)

        cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        cancel_shortcut.activated.connect(self._on_cancel)

        # Initial disabled state (when no single note is loaded)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        self.chk_autosave.setEnabled(enabled)
        self.combo_font_size.setEnabled(enabled)
        self.btn_mode_source.setEnabled(enabled)
        self.btn_mode_preview.setEnabled(enabled)
        self.btn_read_from.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.btn_cancel.setEnabled(enabled)

        if not enabled:
            self.btn_cancel_autosave.hide()
            self.autosave_timer.stop()

    def clear_and_disable(self, message: str):
        self.current_rel_path = ""
        self.ignore_text_changes = True
        self.editor.setPlainText("")
        self.preview_browser.setMarkdown("")
        self.ignore_text_changes = False
        self._set_controls_enabled(False)
        self.lbl_autosave_status.setText("Inactive")
        self.lbl_autosave_status.setStyleSheet("color: #777777; font-size: 11px;")

    def _on_font_size_changed(self, text: str):
        try:
            pt_size = int(text.replace("pt", "").strip())
            self.current_font_size = pt_size

            font_ed = self.editor.font()
            font_ed.setPointSize(pt_size)
            self.editor.setFont(font_ed)
            self.editor.update_line_number_area_width(0)

            self._apply_preview_font_size(pt_size)
        except Exception:
            pass

    def _apply_preview_font_size(self, pt_size: int):
        self.preview_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 12px;
                font-size: {pt_size}pt;
                line-height: 1.5;
            }}
        """)

    def _set_view_mode(self, mode: str):
        self.current_view_mode = mode
        if mode == "source":
            self.btn_mode_source.setChecked(True)
            self.btn_mode_preview.setChecked(False)
            self.editor_stack.setCurrentWidget(self.editor)
        else:
            self.btn_mode_source.setChecked(False)
            self.btn_mode_preview.setChecked(True)
            self.preview_browser.setMarkdown(self.editor.toPlainText())
            self.editor_stack.setCurrentWidget(self.preview_browser)

    def load_note(self, rel_path: str, content: str, available_tags: list = None):
        self.ignore_text_changes = True
        self.current_rel_path = rel_path

        if available_tags:
            self.editor.set_tags_list(available_tags)

        self.editor.setPlainText(content)
        self.preview_browser.setMarkdown(content)

        self._set_controls_enabled(True)
        self._set_view_mode(getattr(self, 'current_view_mode', 'source'))

        # Stop any active timer
        self.autosave_timer.stop()
        self.btn_cancel_autosave.hide()
        self.lbl_autosave_status.setText("Ready")
        self.lbl_autosave_status.setStyleSheet("color: #007acc; font-size: 11px; font-weight: bold;")

        self.ignore_text_changes = False

    def _on_text_changed(self):
        if self.ignore_text_changes or not self.current_rel_path:
            return

        if self.chk_autosave.isChecked():
            self.countdown_seconds = 5
            self.lbl_autosave_status.setText(f"⏳ Auto-saving in {self.countdown_seconds}s...")
            self.lbl_autosave_status.setStyleSheet("color: #e67e22; font-size: 11px; font-weight: bold;")
            self.btn_cancel_autosave.show()
            self.autosave_timer.start()

    def _on_autosave_tick(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds > 0:
            self.lbl_autosave_status.setText(f"⏳ Auto-saving in {self.countdown_seconds}s...")
            self.lbl_autosave_status.setStyleSheet("color: #e67e22; font-size: 11px; font-weight: bold;")
        else:
            self.autosave_timer.stop()
            self.btn_cancel_autosave.hide()
            self._on_save()
            self.lbl_autosave_status.setText("✓ Auto-saved")
            self.lbl_autosave_status.setStyleSheet("color: #2ecc71; font-size: 11px; font-weight: bold;")

    def _cancel_autosave_countdown(self):
        self.autosave_timer.stop()
        self.btn_cancel_autosave.hide()
        self.lbl_autosave_status.setText("⛔ Auto-save cancelled")
        self.lbl_autosave_status.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")

    def _read_tags_from_body(self):
        content = self.editor.toPlainText()
        if not content.strip():
            return

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
            self._on_save()

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
            self._on_save()

            QMessageBox.information(self, "Read URL Success", f"Updated YAML url property to:\n{target_url}")
        except Exception as e:
            QMessageBox.critical(self, "Read URL Error", f"Failed to update YAML url property: {e}")

    def _read_author_from_body(self):
        content = self.editor.toPlainText()
        if not content.strip():
            return

        patterns = [
            r'\*\*(?:Author|By|Written by):\*\*\s*([^\n\r]+)',
            r'(?:^|\n)(?:Author|By|Written by):\s*([^\n\r]+)',
        ]

        found_authors = []
        for pat in patterns:
            matches = re.findall(pat, content, flags=re.IGNORECASE)
            for m in matches:
                clean = m.strip(" *_`#")
                if clean and clean not in found_authors:
                    found_authors.append(clean)

        if not found_authors:
            QMessageBox.information(self, "Read Author", "No author pattern (e.g. **Author:** Name) found in note body text.")
            return

        target_author = ""
        if len(found_authors) == 1:
            target_author = found_authors[0]
        else:
            dlg = UrlSelectionDialog(found_authors, parent=self)
            dlg.setWindowTitle("✍️ Select Author for YAML Property")
            dlg.findChild(QLabel).setText("<b>Multiple author patterns detected. Select which author to set in YAML:</b>")
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_url:
                target_author = dlg.selected_url
            else:
                return

        if not target_author:
            return

        try:
            post = frontmatter.loads(content)
            meta = dict(post.metadata)
            meta["author"] = target_author
            post.metadata = meta

            new_content = frontmatter.dumps(post)
            self.editor.setPlainText(new_content)
            self._on_save()

            QMessageBox.information(self, "Read Author Success", f"Updated YAML author property to:\n{target_author}")
        except Exception as e:
            QMessageBox.critical(self, "Read Author Error", f"Failed to update YAML author property: {e}")

    def _read_created_date_from_file(self):
        content = self.editor.toPlainText()
        if not content.strip() or not self.current_rel_path:
            return

        vault_p = getattr(self.parent(), 'vault_path', '')
        if not vault_p and hasattr(self.parent(), 'parent'):
            vault_p = getattr(self.parent().parent(), 'vault_path', '')

        if not vault_p:
            return

        abs_p = Path(vault_p) / self.current_rel_path
        if not abs_p.exists():
            return

        try:
            stat_info = abs_p.stat()
            ctime = getattr(stat_info, 'st_ctime', stat_info.st_mtime)
            dt = datetime.fromtimestamp(ctime)
            created_str = dt.strftime("%Y-%m-%d %H:%M:%S")

            post = frontmatter.loads(content)
            meta = dict(post.metadata)

            meta["created"] = created_str
            post.metadata = meta

            new_content = frontmatter.dumps(post)
            self.editor.setPlainText(new_content)
            self.preview_browser.setMarkdown(new_content)
            self._on_save()

            QMessageBox.information(
                self, "Capture Created Date Success",
                f"Successfully captured file creation date into YAML frontmatter:\ncreated: {created_str}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Capture Created Date Error", f"Failed to capture created date: {e}")

    def _fix_yaml_tags_in_note(self):
        content = self.editor.toPlainText()
        if not content.strip():
            return

        parsed_tags = []
        post = None

        # 1. Try standard PyYAML parsing first
        try:
            post = frontmatter.loads(content)
            meta = dict(post.metadata)
            raw_tags = meta.get("tags") or meta.get("tag")

            if isinstance(raw_tags, str):
                items = re.split(r"[,;\s]+", raw_tags)
                for it in items:
                    clean = it.strip(" []#\"'")
                    if clean:
                        kebab = re.sub(r'\s+', '-', clean)
                        if kebab and kebab not in parsed_tags:
                            parsed_tags.append(kebab)
            elif isinstance(raw_tags, list):
                for item in raw_tags:
                    if isinstance(item, str):
                        sub_items = re.split(r"[,;\n]+", item)
                        for sub in sub_items:
                            clean = sub.strip(" []#\"'")
                            if clean:
                                kebab = re.sub(r'\s+', '-', clean)
                                if kebab and kebab not in parsed_tags:
                                    parsed_tags.append(kebab)
        except Exception:
            pass

        # 2. Fallback regex extractor for malformed YAML syntax (e.g. tags: - ai, aip)
        if not parsed_tags:
            match = re.search(r'(?:^|\n)(?:tags|tag):\s*(.*?)(?=\n[a-zA-Z0-9_\-]+:|\n---|\Z)', content, re.DOTALL | re.IGNORECASE)
            if match:
                tags_text = match.group(1)
                tokens = re.findall(r'[a-zA-Z0-9_\-\u00C0-\u024F]+', tags_text)
                for tok in tokens:
                    clean = tok.strip(" -#[],\"'")
                    if clean:
                        kebab = re.sub(r'\s+', '-', clean)
                        if kebab and kebab not in parsed_tags:
                            parsed_tags.append(kebab)

        if not parsed_tags:
            QMessageBox.information(self, "Fix YAML Tags", "No tags found in YAML metadata to format.")
            return

        # 3. Rebuild clean frontmatter
        try:
            if not post:
                tag_block = "tags:\n" + "\n".join([f"  - {t}" for t in parsed_tags])
                new_content = re.sub(r'(?:^|\n)(?:tags|tag):\s*(.*?)(?=\n[a-zA-Z0-9_\-]+:|\n---|\Z)', f"\n{tag_block}\n", content, count=1, flags=re.DOTALL | re.IGNORECASE)
                if not new_content.startswith("---"):
                    new_content = f"---\n{new_content.lstrip()}"
            else:
                meta = dict(post.metadata)
                meta["tags"] = parsed_tags
                if "tag" in meta:
                    del meta["tag"]
                post.metadata = meta
                new_content = frontmatter.dumps(post)

            self.editor.setPlainText(new_content)
            self.preview_browser.setMarkdown(new_content)
            self._on_save()

            QMessageBox.information(
                self, "Fix YAML Tags Success",
                f"Successfully formatted {len(parsed_tags)} tag(s) into clean kebab-case list format:\n\n" +
                "\n".join([f"  - {t}" for t in parsed_tags])
            )
        except Exception as e:
            QMessageBox.critical(self, "Fix YAML Tags Error", f"Failed to format YAML frontmatter tags: {e}")

    def _on_save(self):
        if not self.current_rel_path:
            return
        self.autosave_timer.stop()
        self.btn_cancel_autosave.hide()
        content = self.editor.toPlainText()
        self.save_requested.emit(self.current_rel_path, content)

    def _on_cancel(self):
        self.autosave_timer.stop()
        self.btn_cancel_autosave.hide()
        self.clear_and_disable("Editing cancelled")
        self.cancel_requested.emit()
