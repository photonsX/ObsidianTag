import os
import re
import json
import frontmatter
from datetime import datetime
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

        # Table Widget (#, Note Title, YAML Tag Status)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["#", "Note Title", "YAML Tag Status"])
        self.table_widget.setColumnWidth(0, 45)
        self.table_widget.setColumnWidth(2, 130)
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
        self.table_widget.cellClicked.connect(self._on_cell_clicked)
        self.table_widget.itemChanged.connect(self._on_table_item_changed)

        # Enable Context Menu on Note List Table
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._show_context_menu)

        left_layout.addWidget(self.table_widget, stretch=1)

        splitter.addWidget(left_widget)

        # RIGHT PANEL: Permanent NoteEditorPanel (Never resizes or swaps layout!)
        self.editor_panel = NoteEditorPanel(parent=self)
        self.editor_panel.save_requested.connect(self._on_note_saved)
        self.editor_panel.title_renamed.connect(self._rename_note_file)

        splitter.addWidget(self.editor_panel)

        # 45/55 split ratio
        splitter.setSizes([450, 550])
        main_layout.addWidget(splitter, stretch=1)

    def _detect_note_tag_status(self, rel_path: str) -> str:
        if not self.vault_path:
            return "NO_YAML"
        abs_p = Path(self.vault_path) / rel_path
        if not abs_p.exists():
            return "NO_YAML"
        try:
            with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                raw_content = f.read()

            post = frontmatter.loads(raw_content)
            meta = dict(post.metadata)

            # If note has NO frontmatter block (empty metadata dictionary)
            if not meta:
                return "NO_YAML"

            # Check if tags field uses singular 'tag' key instead of 'tags'
            if "tag" in meta and "tags" not in meta:
                return "NEEDS_FIX"

            raw_tags = meta.get("tags")

            if raw_tags is not None:
                # Raw string instead of clean YAML list
                if isinstance(raw_tags, str):
                    return "NEEDS_FIX"

                # List elements containing spaces, commas, or hashtags
                if isinstance(raw_tags, list):
                    for t in raw_tags:
                        if not isinstance(t, str):
                            return "NEEDS_FIX"
                        if " " in t or "," in t or t.startswith("#"):
                            return "NEEDS_FIX"

            # Note has valid YAML frontmatter metadata (e.g. bucket: dailynote)
            return "VALID"
        except Exception:
            return "NO_YAML"

    def _on_cell_clicked(self, row: int, col: int):
        if col == 2 and 0 <= row < len(self.notes_data):
            item = self.table_widget.item(row, 2)
            if item and "Fix" in item.text():
                self._batch_fix_yaml_tags([row])

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
            item_title.setFlags(item_title.flags() | Qt.ItemFlag.ItemIsEditable)
            item_title.setData(Qt.ItemDataRole.UserRole, n["path"])
            if n["is_ambiguous"]:
                item_title.setForeground(QColor("#e67e22"))
            self.table_widget.setItem(row_idx, 1, item_title)

            # 2. YAML Tag Status
            status_code = self._detect_note_tag_status(n["path"])
            if status_code == "NEEDS_FIX":
                item_status = QTableWidgetItem("🛠️ Fix")
                item_status.setForeground(QColor("#e67e22"))
                item_status.setToolTip("Click to fix YAML tags into kebab-case list format")
            elif status_code == "NO_YAML":
                item_status = QTableWidgetItem("🚫 No YAML")
                item_status.setForeground(QColor("#777777"))
                item_status.setToolTip("No YAML tags present in frontmatter")
            else:
                item_status = QTableWidgetItem("✅ Valid")
                item_status.setForeground(QColor("#2ecc71"))
                item_status.setToolTip("YAML tags are clean and valid")

            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_widget.setItem(row_idx, 2, item_status)

            # Re-select row if path matched
            if n["path"] in saved_paths:
                item_title.setSelected(True)
                item_num.setSelected(True)
                item_status.setSelected(True)

        self.ignore_cell_signals = False
        self.table_widget.verticalScrollBar().setValue(v_scroll)
        self._on_table_selection_changed()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if self.ignore_cell_signals or item.column() != 1:
            return
        row = item.row()
        if 0 <= row < len(self.notes_data):
            old_rel_path = self.notes_data[row]["path"]
            raw_text = item.text()
            clean_title = raw_text.replace("📄 ", "").replace("⚠️ ", "").replace(" (Flagged)", "").strip()
            self._rename_note_file(old_rel_path, clean_title)

    def _rename_note_file(self, old_rel_path: str, new_title_str: str):
        if not self.vault_path or not old_rel_path:
            return

        clean_title = re.sub(r'[\\/:*?"<>|]', '', new_title_str).strip()
        if not clean_title:
            return

        old_rel = Path(old_rel_path)
        old_abs = Path(self.vault_path) / old_rel

        if not old_abs.exists():
            return

        new_filename = f"{clean_title}.md"
        new_rel = old_rel.parent / new_filename if str(old_rel.parent) != "." else Path(new_filename)
        new_abs = Path(self.vault_path) / new_rel

        if old_abs.resolve() == new_abs.resolve():
            return

        if new_abs.exists():
            QMessageBox.warning(self, "Rename Failed", f"A note file named '{new_filename}' already exists!")
            self.load_data()
            return

        try:
            old_abs.rename(new_abs)

            self.cache_manager.remove_file(str(old_rel).replace("\\", "/"))
            updated_note = VaultScanner.scan_file(new_abs, Path(self.vault_path))
            if updated_note:
                self.cache_manager.incremental_update_file(updated_note)

            self.yaml_updated.emit()
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", f"Failed to rename note file on disk: {e}")
            self.load_data()

    def _open_in_explorer(self, row: int):
        if not self.vault_path or not (0 <= row < len(self.notes_data)):
            return
        n = self.notes_data[row]
        abs_p = (Path(self.vault_path) / n["path"]).resolve()
        if abs_p.exists():
            import subprocess
            subprocess.Popen(f'explorer /select,"{abs_p}"')

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

        # 0. Refresh List Action
        act_refresh = menu.addAction("🔄 Refresh List")
        act_refresh.triggered.connect(self._refresh_vault_and_list)

        menu.addSeparator()

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

        # 5. Capture Created Date Action
        act_date = menu.addAction("📅 Capture Created Date (Set created: in YAML)")
        act_date.triggered.connect(lambda _, rows=selected_rows: self._batch_capture_created_date(rows))

        # 6. Fix YAML Tags Action
        act_fix = menu.addAction("🛠️ Fix YAML Tags (Kebab-case List Format)")
        act_fix.triggered.connect(lambda _, rows=selected_rows: self._batch_fix_yaml_tags(rows))

        menu.addSeparator()

        # 7. View in File Explorer Action
        act_explorer = menu.addAction("📂 View in File Explorer")
        act_explorer.triggered.connect(lambda _, row=clicked_row: self._open_in_explorer(row))

        menu.exec(self.table_widget.viewport().mapToGlobal(pos))

    def _batch_capture_created_date(self, rows: List[int]):
        for r in rows:
            if 0 <= r < len(self.notes_data):
                n = self.notes_data[r]
                rel_p = n["path"]
                abs_p = Path(self.vault_path) / rel_p

                if not abs_p.exists():
                    continue

                try:
                    stat_info = abs_p.stat()
                    ctime = getattr(stat_info, 'st_ctime', stat_info.st_mtime)
                    dt = datetime.fromtimestamp(ctime)
                    created_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                    with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                        raw_content = f.read()

                    post = frontmatter.loads(raw_content)
                    meta = dict(post.metadata)
                    meta["created"] = created_str
                    post.metadata = meta

                    new_text = frontmatter.dumps(post)
                    with open(abs_p, "w", encoding="utf-8") as f:
                        f.write(new_text)

                    updated_note = VaultScanner.scan_file(abs_p, Path(self.vault_path))
                    if updated_note:
                        self.cache_manager.incremental_update_file(updated_note)
                except Exception as e:
                    print(f"Error capturing created date for {rel_p}: {e}")

        self.yaml_updated.emit()
        self.load_data()

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

                    parsed_tags = []
                    post = None

                    try:
                        post = frontmatter.loads(raw_content)
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

                    if not parsed_tags:
                        match = re.search(r'(?:^|\n)(?:tags|tag):\s*(.*?)(?=\n[a-zA-Z0-9_\-]+:|\n---|\Z)', raw_content, re.DOTALL | re.IGNORECASE)
                        if match:
                            tags_text = match.group(1)
                            tokens = re.findall(r'[a-zA-Z0-9_\-\u00C0-\u024F]+', tags_text)
                            for tok in tokens:
                                clean = tok.strip(" -#[],\"'")
                                if clean:
                                    kebab = re.sub(r'\s+', '-', clean)
                                    if kebab and kebab not in parsed_tags:
                                        parsed_tags.append(kebab)

                    if parsed_tags:
                        if not post:
                            tag_block = "tags:\n" + "\n".join([f"  - {t}" for t in parsed_tags])
                            new_text = re.sub(r'(?:^|\n)(?:tags|tag):\s*(.*?)(?=\n[a-zA-Z0-9_\-]+:|\n---|\Z)', f"\n{tag_block}\n", raw_content, count=1, flags=re.DOTALL | re.IGNORECASE)
                            if not new_text.startswith("---"):
                                new_text = f"---\n{new_text.lstrip()}"
                        else:
                            meta = dict(post.metadata)
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

    def _refresh_vault_and_list(self):
        if self.vault_path:
            VaultScanner.scan_vault(Path(self.vault_path), self.cache_manager)
            self.yaml_updated.emit()
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

                if not abs_path.exists():
                    # File was deleted externally on disk! Remove from cache and refresh table cleanly.
                    self.cache_manager.remove_file(rel_path)
                    self.yaml_updated.emit()
                    self.editor_panel.clear_and_disable("Note file was deleted externally")
                    self.load_data()
                    return

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
        if not abs_path.exists():
            self.cache_manager.remove_file(rel_path)
            self.yaml_updated.emit()
            self.editor_panel.clear_and_disable("Note file no longer exists on disk")
            self.load_data()
            return

        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            updated_note = VaultScanner.scan_file(abs_path, Path(self.vault_path))
            if updated_note:
                self.cache_manager.incremental_update_file(updated_note)

            self.yaml_updated.emit()
        except Exception as e:
            print(f"Error saving note in YamlManagerWidget: {e}")
