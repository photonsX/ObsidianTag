from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QIcon

class SearchBar(QWidget):
    search_changed = pyqtSignal(str)

    def __init__(self, parent=None, debounce_ms=300):
        super().__init__(parent)
        self.debounce_ms = debounce_ms

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Search tags (#project) or note titles...")
        self.input_edit.setClearButtonEnabled(True)
        self.input_edit.setMinimumHeight(32)

        # Style search box matching Obsidian dark theme
        self.input_edit.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #007acc;
                background-color: #1e1e1e;
            }
        """)

        self.layout.addWidget(self.input_edit)

        # Debounce timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._emit_search)

        self.input_edit.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str):
        self.timer.stop()
        self.timer.start(self.debounce_ms)

    def _emit_search(self):
        text = self.input_edit.text().strip()
        self.search_changed.emit(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clear_search()
            event.accept()
        else:
            super().keyPressEvent(event)

    def clear_search(self):
        self.input_edit.clear()
        self.input_edit.setFocus()
        self.search_changed.emit("")

    def text(self) -> str:
        return self.input_edit.text().strip()
