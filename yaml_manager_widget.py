import os
import re
import json
import frontmatter
from pathlib import Path
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QFrame, QHeaderView, QSplitter, QStackedWidget, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from cache_manager import CacheManager
from vault_scanner import VaultScanner
from note_editor import NoteEditorPanel


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

        # Splitter to divide page into 2 panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #333333;
                width: 3px;
            }
            QSplitter::handle:hover {
                background-color: #0e639c;
            }
        """)

        # LEFT PANEL: Excel Filter & Note List Table
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Excel Filter Header Frame
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
        self.search_input.returnPressed.connect(self._focus_table)
        filter_row.addWidget(self.search_input, stretch=1)

        left_layout.addWidget(header_frame)

        # Table Widget (# and Note Title columns only)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(["#", "Note Title"])
        self.table_widget.setColumnWidth(0, 45)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

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
        self.table_widget.itemSelectionChanged.connect(self._on_table_selection_changed)

        # Enable Context Menu on Note List Table
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._show_context_menu)

        left_layout.addWidget(self.table_widget, stretch=1)

        splitter.addWidget(left_widget)

        # RIGHT PANEL: Permanent NoteEditorPanel (Never resizes or swaps layout!)
        self.editor_panel = NoteEditorPanel(parent=self)
        self.editor_panel.save_requested.connect(self._on_note_saved)

        splitter.addWidget(self.editor_panel)

        # 45/55 split ratio
        splitter.setSizes([450, 550])
        main_layout.addWidget(splitter, stretch=1)

    def load_data(self):
        v_scroll = self.table_widget.verticalScrollBar().value()
        selected_rows = self._get_selected_rows()
        saved_paths = set()
        for r in selected_rows:
            if 0 <= r < len(self.notes_data):
                saved_paths.add(self.notes_data[r]["path"])

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

            # Re-select row if path matched
            if n["path"] in saved_paths:
                item_title.setSelected(True)
                item_num.setSelected(True)

        self.ignore_cell_signals = False
        self.table_widget.verticalScrollBar().setValue(v_scroll)
        self._on_table_selection_changed()

    def _focus_table(self):
        if self.table_widget.rowCount() > 0:
            self.table_widget.setFocus()
            if not self._get_selected_rows():
                self.table_widget.selectRow(0)

    def _get_selected_rows(self) -> List[int]:
        selected_rows = set()
        if self.table_widget.selectionModel():
            for idx in self.table_widget.selectionModel().selectedRows():
                selected_rows.add(idx.row())
        for item in self.table_widget.selectedItems():
            selected_rows.add(item.row())
        return sorted(list(selected_rows))

    def _show_context_menu(self, pos):
        item = self.table_widget.itemAt(pos)
        if not item:
            return

        clicked_row = item.row()
        selected_rows = self._get_selected_rows()

        if clicked_row not in selected_rows:
            self.table_widget.clearSelection()
            self.table_widget.selectRow(clicked_row)
            selected_rows = [clicked_row]

        if not selected_rows:
            return

        count_str = f"{len(selected_rows)} note(s)"

        menu = QMenu(self)
        menu.setStyleSheet("""
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
            QMenu::separator {
                height: 1px;
                background-color: #333333;
                margin: 4px 0px;
            }
        """)

        # Header Title
        lbl_header = menu.addAction(f"⚡ Batch Update ({count_str})")
        lbl_header.setEnabled(False)
        menu.addSeparator()

        # 1. Bucket Submenu
        bucket_menu = menu.addMenu("📁 Set Bucket")
        buckets = ["note", "idea", "wip", "task", "dailynote"]
        for b in buckets:
            act = bucket_menu.addAction(b)
            act.triggered.connect(lambda _, val=b, rows=selected_rows: self._batch_apply_yaml_key("bucket", val, rows))

        # 2. Status Submenu
        status_menu = menu.addMenu("🔥 Set Status (Heat)")
        statuses = [("🔥 hot", "hot"), ("☀️ warm", "warm"), ("❄️ cool", "cool"), ("🧊 cold", "cold")]
        for label, val in statuses:
            act = status_menu.addAction(label)
            act.triggered.connect(lambda _, val=val, rows=selected_rows: self._batch_apply_yaml_key("status", val, rows))

        # 3. Attention Submenu
        att_menu = menu.addMenu("⚡ Set Attention")
        attentions = [("✅ settled", "settled"), ("⚡ needs-revisit", "needs-revisit"), ("📌 pinned", "pinned")]
        for label, val in attentions:
            act = att_menu.addAction(label)
            act.triggered.connect(lambda _, val=val, rows=selected_rows: self._batch_apply_yaml_key("attention", val, rows))

        menu.addSeparator()

        # 4. Add URL Property Action
        act_url = menu.addAction("🔗 Add URL Property")
        act_url.triggered.connect(lambda _, rows=selected_rows: self._batch_add_url_property(rows))

        # 5. Fix YAML Tags Action
        act_fix = menu.addAction("🛠️ Fix YAML Tags (Kebab-case List Format)")
        act_fix.triggered.connect(lambda _, rows=selected_rows: self._batch_fix_yaml_tags(rows))

        menu.exec(self.table_widget.viewport().mapToGlobal(pos))

    def _batch_fix_yaml_tags(self, rows: List[int]):
        for r in rows:
            if 0 <= r < len(self.notes_data):
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

                    raw_tags = meta.get("tags") or meta.get("tag")
                    parsed_tags = []

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

                    if parsed_tags:
                        meta["tags"] = parsed_tags
                        if "tag" in meta:
                            del meta["tag"]
                        post.metadata = meta

                        new_text = frontmatter.dumps(post)
                        with open(abs_p, "w", encoding="utf-8") as f:
                            f.write(new_text)

                        updated_note = VaultScanner.scan_file(abs_p, Path(self.vault_path))
                        if updated_note:
                            self.cache_manager.incremental_update_file(updated_note)
                except Exception as e:
                    print(f"Error fixing YAML tags for {rel_p}: {e}")

        self.yaml_updated.emit()
        self.load_data()

    def _batch_add_url_property(self, rows: List[int]):
        for r in rows:
            if 0 <= r < len(self.notes_data):
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

                    # Set url property: use detected_body_url if present, else default "url here"
                    detected = n.get("detected_body_url", "").strip()
                    meta["url"] = detected if detected else "url here"

                    post.metadata = meta
                    new_text = frontmatter.dumps(post)

                    with open(abs_p, "w", encoding="utf-8") as f:
                        f.write(new_text)

                    updated_note = VaultScanner.scan_file(abs_p, Path(self.vault_path))
                    if updated_note:
                        self.cache_manager.incremental_update_file(updated_note)
                except Exception as e:
                    print(f"Error adding URL property to {rel_p}: {e}")

        self.yaml_updated.emit()
        self.load_data()

    def _batch_apply_yaml_key(self, key: str, value: str, rows: List[int]):
        for r in rows:
            if 0 <= r < len(self.notes_data):
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
                    print(f"Error saving batch YAML for {rel_p}: {e}")

        # Emit signal to refresh Tab 1 & Tab 2
        self.yaml_updated.emit()

        # Reload data & update live preview if 1 note selected
        self.load_data()

    def _on_table_selection_changed(self):
        if self.ignore_cell_signals:
            return

        selected_rows = self._get_selected_rows()

        if len(selected_rows) == 1:
            row_idx = selected_rows[0]
            if 0 <= row_idx < len(self.notes_data):
                note_info = self.notes_data[row_idx]
                rel_path = note_info["path"]
                abs_path = Path(self.vault_path) / rel_path

                if abs_path.exists():
                    try:
                        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()

                        stats = self.cache_manager.get_tag_stats()
                        all_tags = [t.name for t in stats.all_tags] if hasattr(stats, 'all_tags') else []

                        self.editor_panel.load_note(rel_path, content, all_tags)
                        return
                    except Exception as e:
                        print(f"Error reading note preview: {e}")

        elif len(selected_rows) > 1:
            self.editor_panel.clear_and_disable(f"Multiple notes selected ({len(selected_rows)} notes)")
        else:
            self.editor_panel.clear_and_disable("Select a single note to preview")

    def _on_note_saved(self, rel_path: str, new_content: str):
        if not self.vault_path:
            return

        abs_path = Path(self.vault_path) / rel_path
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            updated_note = VaultScanner.scan_file(abs_path, Path(self.vault_path))
            if updated_note:
                self.cache_manager.incremental_update_file(updated_note)

            self.yaml_updated.emit()
        except Exception as e:
            print(f"Error saving note in YamlManagerWidget: {e}")
