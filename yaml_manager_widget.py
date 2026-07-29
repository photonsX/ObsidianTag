import os
import re
import json
import frontmatter
from pathlib import Path
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QFrame, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from cache_manager import CacheManager
from vault_scanner import VaultScanner


class YamlManagerWidget(QWidget):
    yaml_updated = pyqtSignal()

    def __init__(self, cache_manager: CacheManager, vault_path: str = "", parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.vault_path = vault_path
        self.notes_data: List[dict] = []
        self.ignore_cell_signals = False

        self.setup_ui()
        self.load_data()

    def set_vault_path(self, path: str):
        self.vault_path = path
        self.load_data()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Excel Filter Header Frame: Search Line Edit Only
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLabel {
                color: #cccccc;
                font-weight: bold;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)

        filter_row = QHBoxLayout(header_frame)
        filter_row.setContentsMargins(4, 4, 4, 4)
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel("<b>Excel Filter:</b>"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter note title or relative path...")
        self.search_input.textChanged.connect(self.load_data)
        filter_row.addWidget(self.search_input, stretch=1)

        main_layout.addWidget(header_frame)

        # Table Widget (# and Note Title columns only)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(["#", "Note Title"])
        self.table_widget.setColumnWidth(0, 50)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Spreadsheet styling: Crisp grid lines, alternating rows, compact row height
        self.table_widget.setShowGrid(True)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.verticalHeader().setDefaultSectionSize(28)
        self.table_widget.verticalHeader().setVisible(False)

        self.table_widget.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                alternate-background-color: #242424;
                color: #d4d4d4;
                gridline-color: #333333;
                border: 1px solid #333333;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #cccccc;
                padding: 4px;
                border: 1px solid #333333;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 2px 6px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #0e639c;
                color: #ffffff;
            }
        """)
        main_layout.addWidget(self.table_widget, stretch=1)

    def load_data(self):
        self.ignore_cell_signals = True
        query = self.search_input.text().strip()

        self.notes_data = self.cache_manager.get_all_yaml_notes(
            filter_query=query
        )

        self.table_widget.setRowCount(0)
        self.table_widget.setRowCount(len(self.notes_data))

        for row_idx, n in enumerate(self.notes_data):
            # 0. Row #
            item_num = QTableWidgetItem(str(row_idx + 1))
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_num.setForeground(QColor("#777777"))
            self.table_widget.setItem(row_idx, 0, item_num)

            # 1. Note Title
            title_text = f"📄 {n['title']}"
            if n["is_ambiguous"]:
                title_text = f"⚠️ {n['title']} (Flagged)"
            item_title = QTableWidgetItem(title_text)
            item_title.setData(Qt.ItemDataRole.UserRole, n["path"])
            if n["is_ambiguous"]:
                item_title.setForeground(QColor("#e67e22"))
            self.table_widget.setItem(row_idx, 1, item_title)

        self.ignore_cell_signals = False
