import os
import re
import json
import frontmatter
from pathlib import Path
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QLineEdit, QPushButton, QLabel, QCheckBox, QFrame,
    QDialog, QSplitter, QPlainTextEdit, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont

from cache_manager import CacheManager
from models import Note
from vault_scanner import VaultScanner


class YamlResolutionDialog(QDialog):
    """
    Floating dialog that pops up when a note's frontmatter is flagged as ambiguous or unparseable.
    Allows side-by-side raw YAML editing and dropdown field mapping.
    """
    resolved = pyqtSignal(str)  # Emits rel_path on save

    def __init__(self, rel_path: str, vault_path: str, cache_manager: CacheManager, parent=None):
        super().__init__(parent)
        self.rel_path = rel_path
        self.vault_path = vault_path
        self.cache_manager = cache_manager
        self.abs_path = Path(vault_path) / rel_path

        self.setWindowTitle(f"🛠️ Resolve Frontmatter — {Path(rel_path).name}")
        self.resize(800, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QComboBox, QLineEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

        self.setup_ui()
        self.load_file_data()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header info
        lbl_info = QLabel(
            f"<b>Flagged File:</b> <code>{self.rel_path}</code><br>"
            "<span style='color:#e67e22;'>⚠️ The frontmatter has non-standard values or custom format. Map the fields or clean the raw YAML below:</span>"
        )
        main_layout.addWidget(lbl_info)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Raw File Content / Frontmatter Editor
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("<b>Raw Note Header Content:</b>"))
        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setFont(QFont("Consolas", 11))
        self.raw_editor.setStyleSheet("background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c;")
        left_layout.addWidget(self.raw_editor)
        splitter.addWidget(left_widget)

        # Right: Dropdown Field Mapper
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        right_layout.addWidget(QLabel("<b>Map Standard YAML Fields:</b>"))

        # Bucket Dropdown
        h_bucket = QHBoxLayout()
        h_bucket.addWidget(QLabel("Bucket:"))
        self.combo_bucket = QComboBox()
        self.combo_bucket.addItems(["note", "idea", "wip", "task", "dailynote"])
        h_bucket.addWidget(self.combo_bucket)
        right_layout.addLayout(h_bucket)

        # Status Dropdown
        h_status = QHBoxLayout()
        h_status.addWidget(QLabel("Status (Heat):"))
        self.combo_status = QComboBox()
        self.combo_status.addItems(["🔥 hot", "☀️ warm", "❄️ cool", "🧊 cold"])
        h_status.addWidget(self.combo_status)
        right_layout.addLayout(h_status)

        # Attention Dropdown
        h_att = QHBoxLayout()
        h_att.addWidget(QLabel("Attention:"))
        self.combo_attention = QComboBox()
        self.combo_attention.addItems(["✅ settled", "⚡ needs-revisit", "📌 pinned"])
        h_att.addWidget(self.combo_attention)
        right_layout.addLayout(h_att)

        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setSizes([420, 380])
        main_layout.addWidget(splitter, stretch=1)

        # Actions Row
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #3c3c3c;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Resolve & Save Standardized YAML")
        btn_save.clicked.connect(self.save_and_resolve)
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    def load_file_data(self):
        if not self.abs_path.exists():
            return
        try:
            with open(self.abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.raw_editor.setPlainText(content)

            note = VaultScanner.scan_file(self.abs_path, Path(self.vault_path))
            if note:
                idx_b = self.combo_bucket.findText(note.bucket)
                if idx_b >= 0:
                    self.combo_bucket.setCurrentIndex(idx_b)

                # Status mapping
                st_map = {"hot": 0, "warm": 1, "cool": 2, "cold": 3}
                self.combo_status.setCurrentIndex(st_map.get(note.status, 0))

                # Attention mapping
                att_map = {"settled": 0, "needs-revisit": 1, "pinned": 2}
                self.combo_attention.setCurrentIndex(att_map.get(note.attention, 0))

        except Exception as e:
            QMessageBox.warning(self, "Read Error", f"Could not read note: {e}")

    def save_and_resolve(self):
        try:
            with open(self.abs_path, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()

            post = frontmatter.loads(raw_text)
            meta = dict(post.metadata)

            meta["bucket"] = self.combo_bucket.currentText()

            st_text = self.combo_status.currentText()
            clean_st = "hot" if "hot" in st_text else ("warm" if "warm" in st_text else ("cool" if "cool" in st_text else "cold"))
            meta["status"] = clean_st

            att_text = self.combo_attention.currentText()
            clean_att = "settled" if "settled" in att_text else ("needs-revisit" if "needs-revisit" in att_text else "pinned")
            meta["attention"] = clean_att

            post.metadata = meta
            new_content = frontmatter.dumps(post)

            with open(self.abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            updated_note = VaultScanner.scan_file(self.abs_path, Path(self.vault_path))
            if updated_note:
                updated_note.is_ambiguous = False
                self.cache_manager.incremental_update_file(updated_note)

            self.resolved.emit(self.rel_path)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save resolved frontmatter: {e}")


class YamlManagerWidget(QWidget):
    yaml_updated = pyqtSignal()

    def __init__(self, cache_manager: CacheManager, vault_path: str = "", parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.vault_path = vault_path
        self.notes_data: List[dict] = []
        self.saved_selected_paths: set = set()
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

        # Excel-Style Header Frame: Clean Filter Bar
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
            QLineEdit, QComboBox {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QCheckBox {
                color: #cccccc;
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

        self.combo_filter_bucket = QComboBox()
        self.combo_filter_bucket.addItems(["Bucket: All", "note", "idea", "wip", "task", "dailynote"])
        self.combo_filter_bucket.currentIndexChanged.connect(self.load_data)
        filter_row.addWidget(self.combo_filter_bucket)

        self.combo_filter_status = QComboBox()
        self.combo_filter_status.addItems(["Status: All", "hot", "warm", "cool", "cold"])
        self.combo_filter_status.currentIndexChanged.connect(self.load_data)
        filter_row.addWidget(self.combo_filter_status)

        self.combo_filter_att = QComboBox()
        self.combo_filter_att.addItems(["Attention: All", "settled", "needs-revisit", "pinned"])
        self.combo_filter_att.currentIndexChanged.connect(self.load_data)
        filter_row.addWidget(self.combo_filter_att)

        self.chk_only_ambiguous = QCheckBox("⚠️ Flagged Only")
        self.chk_only_ambiguous.setStyleSheet("color: #e67e22; font-weight: bold;")
        self.chk_only_ambiguous.stateChanged.connect(self.load_data)
        filter_row.addWidget(self.chk_only_ambiguous)

        main_layout.addWidget(header_frame)

        # Excel Grid Table Widget (Clean: Only #, Note Title, Bucket, Status, Attention)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(5)
        self.table_widget.setHorizontalHeaderLabels([
            "#", "Note Title", "Bucket ▼", "Status (Heat) ▼", "Attention ▼"
        ])
        self.table_widget.setColumnWidth(0, 45)
        self.table_widget.setColumnWidth(2, 130)
        self.table_widget.setColumnWidth(3, 130)
        self.table_widget.setColumnWidth(4, 140)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Spreadsheet styling: Crisp grid lines, alternating rows, compact 28px height
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
            QComboBox {
                background-color: #2a2a2a;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 2px;
                padding: 1px 4px;
                font-size: 11px;
            }
        """)
        self.table_widget.itemSelectionChanged.connect(self._on_table_selection_changed)
        main_layout.addWidget(self.table_widget, stretch=1)

    def _on_table_selection_changed(self):
        if self.ignore_cell_signals:
            return
        selected_paths = set()
        if self.table_widget.selectionModel():
            for idx in self.table_widget.selectionModel().selectedRows():
                r = idx.row()
                if 0 <= r < len(self.notes_data):
                    selected_paths.add(self.notes_data[r]["path"])
        for item in self.table_widget.selectedItems():
            r = item.row()
            if 0 <= r < len(self.notes_data):
                selected_paths.add(self.notes_data[r]["path"])

        if selected_paths:
            self.saved_selected_paths = selected_paths

    def load_data(self):
        self.ignore_cell_signals = True
        query = self.search_input.text().strip()

        b_text = self.combo_filter_bucket.currentText().replace("Bucket: ", "")
        st_text = self.combo_filter_status.currentText().replace("Status: ", "")
        att_text = self.combo_filter_att.currentText().replace("Attention: ", "")

        only_amb = self.chk_only_ambiguous.isChecked()

        self.notes_data = self.cache_manager.get_all_yaml_notes(
            bucket_filter=b_text,
            status_filter=st_text,
            attention_filter=att_text,
            filter_query=query,
            only_ambiguous=only_amb,
            only_url_detected=False
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
                title_text = f"⚠️ {n['title']} (Flagged - Double click to fix)"
            item_title = QTableWidgetItem(title_text)
            item_title.setData(Qt.ItemDataRole.UserRole, n["path"])
            if n["is_ambiguous"]:
                item_title.setForeground(QColor("#e67e22"))
            self.table_widget.setItem(row_idx, 1, item_title)

            # Apply selection state if path in saved selection
            if n["path"] in self.saved_selected_paths:
                item_num.setSelected(True)
                item_title.setSelected(True)

            # 2. Bucket Dropdown
            combo_b = QComboBox()
            combo_b.addItems(["note", "idea", "wip", "task", "dailynote"])
            idx_b = combo_b.findText(n["bucket"])
            if idx_b >= 0:
                combo_b.setCurrentIndex(idx_b)
            combo_b.currentIndexChanged.connect(lambda _, r=row_idx, c=combo_b: self._on_row_yaml_changed(r, "bucket", c.currentText()))
            self.table_widget.setCellWidget(row_idx, 2, combo_b)

            # 3. Status (Heat) Dropdown
            combo_s = QComboBox()
            combo_s.addItems(["🔥 hot", "☀️ warm", "❄️ cool", "🧊 cold"])
            st_map = {"hot": 0, "warm": 1, "cool": 2, "cold": 3}
            combo_s.setCurrentIndex(st_map.get(n["status"], 0))
            combo_s.currentIndexChanged.connect(lambda _, r=row_idx, c=combo_s: self._on_row_status_changed(r, c.currentText()))
            self.table_widget.setCellWidget(row_idx, 3, combo_s)

            # 4. Attention Dropdown
            combo_a = QComboBox()
            combo_a.addItems(["✅ settled", "⚡ needs-revisit", "📌 pinned"])
            att_map = {"settled": 0, "needs-revisit": 1, "pinned": 2}
            combo_a.setCurrentIndex(att_map.get(n["attention"], 0))
            combo_a.currentIndexChanged.connect(lambda _, r=row_idx, c=combo_a: self._on_row_attention_changed(r, c.currentText()))
            self.table_widget.setCellWidget(row_idx, 4, combo_a)

        self.ignore_cell_signals = False

    def open_resolution_dialog(self, rel_path: str):
        dialog = YamlResolutionDialog(rel_path, self.vault_path, self.cache_manager, parent=self)
        dialog.resolved.connect(lambda: self.load_data())
        dialog.exec()

    def _get_selected_row_indices(self, trigger_row: Optional[int] = None) -> List[int]:
        selected_set = set()

        # 1. From saved_selected_paths
        if self.saved_selected_paths:
            for idx, n in enumerate(self.notes_data):
                if n["path"] in self.saved_selected_paths:
                    selected_set.add(idx)

        # 2. From active selection model
        if self.table_widget.selectionModel():
            for model_index in self.table_widget.selectionModel().selectedRows():
                selected_set.add(model_index.row())
            for item in self.table_widget.selectedItems():
                selected_set.add(item.row())

        # 3. Include trigger row if specified
        if trigger_row is not None:
            selected_set.add(trigger_row)

        return sorted(list(selected_set))

    def _on_row_status_changed(self, row_idx: int, text: str):
        clean_st = "hot" if "hot" in text else ("warm" if "warm" in text else ("cool" if "cool" in text else "cold"))
        self._on_row_yaml_changed(row_idx, "status", clean_st)

    def _on_row_attention_changed(self, row_idx: int, text: str):
        clean_att = "settled" if "settled" in text else ("needs-revisit" if "needs-revisit" in text else "pinned")
        self._on_row_yaml_changed(row_idx, "attention", clean_att)

    def _on_row_yaml_changed(self, row_idx: int, key: str, value):
        if self.ignore_cell_signals:
            return

        target_rows = self._get_selected_row_indices(trigger_row=row_idx)

        for r in target_rows:
            if r < 0 or r >= len(self.notes_data):
                continue
            n = self.notes_data[r]
            rel_p = n["path"]
            abs_p = Path(self.vault_path) / rel_p

            if not abs_p.exists():
                continue

            try:
                with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                    raw_content = f.read()

                post = frontmatter.loads(raw_content)
                meta = dict(post.metadata)
                meta[key] = value
                post.metadata = meta
                new_text = frontmatter.dumps(post)

                with open(abs_p, "w", encoding="utf-8") as f:
                    f.write(new_text)

                updated_note = VaultScanner.scan_file(abs_p, Path(self.vault_path))
                if updated_note:
                    self.cache_manager.incremental_update_file(updated_note)
            except Exception as e:
                print(f"Error saving row change for {rel_p}: {e}")

        # Refresh UI after multi-row update
        self.load_data()
        self.yaml_updated.emit()
