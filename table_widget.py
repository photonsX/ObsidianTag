import os
import re
import frontmatter
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
    QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCompleter, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QBrush, QAction

from color_manager import ColorManager
from cache_manager import CacheManager
from vault_scanner import VaultScanner


class AddTagDialog(QDialog):
    """
    Floating dialog popup styled in dark theme allowing users to select an existing tag
    via autocomplete or type a new tag to apply to selected note(s).
    """
    def __init__(self, existing_tags: List[str], target_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🏷️ Add Tag to Note(s)")
        self.resize(420, 160)
        self.selected_tag = ""

        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #252526;
                color: #ffffff;
                border: 1px solid #007acc;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        count_text = f"Adding tag to <b>{target_count}</b> selected note(s):" if target_count > 1 else "Adding tag to note:"
        lbl_info = QLabel(count_text)
        layout.addWidget(lbl_info)

        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Type existing tag or new tag name...")

        clean_tags = [t if not t.startswith("#") else t[1:] for t in existing_tags]
        completer = QCompleter(clean_tags, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.tag_input.setCompleter(completer)

        layout.addWidget(self.tag_input)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet("background-color: #3c3c3c;")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_add = QPushButton("➕ Add Tag")
        btn_add.clicked.connect(self._on_accept)
        btn_box.addWidget(btn_add)

        layout.addLayout(btn_box)

        self.tag_input.returnPressed.connect(self._on_accept)

    def _on_accept(self):
        val = self.tag_input.text().strip()
        if val:
            if val.startswith("#"):
                val = val[1:].strip()
            self.selected_tag = val
            self.accept()


class TagTableWidget(QTreeWidget):
    note_double_clicked = pyqtSignal(str)  # rel_path
    status_message = pyqtSignal(str)
    tags_updated = pyqtSignal()

    def __init__(self, cache_manager: CacheManager, vault_path: str = "", parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.vault_path = str(vault_path) if vault_path else ""
        self.current_filter = ""
        self.sort_order = "count_desc"
        self.show_empty = False
        self.show_orphans = True

        self.init_ui()

    def set_vault_path(self, path: str):
        if path:
            self.vault_path = str(path)

    def init_ui(self):
        self.setColumnCount(3)
        self.setHeaderLabels(["TAG / NOTE", "COUNT", "SHARED TAGS"])

        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 320)
        self.setColumnWidth(1, 80)

        self.setAnimated(True)
        self.setIndentation(20)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(True)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 4px 6px;
                border-bottom: 1px solid #282828;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
                color: #ffffff;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #007acc;
                padding: 6px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #3c3c3c;
            }
        """)

        self.itemExpanded.connect(self._on_item_expanded)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def reload_tags(self, filter_query="", sort_by="count_desc", show_empty=False, show_orphans=True):
        self.current_filter = filter_query
        self.sort_order = sort_by
        self.show_empty = show_empty
        self.show_orphans = show_orphans

        expanded_tags = set()
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item and item.isExpanded():
                tag_name = item.data(0, Qt.ItemDataRole.UserRole)
                if tag_name:
                    expanded_tags.add(tag_name)

        self.clear()

        tags = self.cache_manager.get_all_tags(
            sort_by=self.sort_order,
            filter_query=self.current_filter,
            show_empty=self.show_empty,
            show_orphans=self.show_orphans
        )

        for t in tags:
            tag_name = t["name"]
            display_name = f"#{tag_name}"
            color_hex = ColorManager.get_color(tag_name)
            color_icon = ColorManager.create_color_icon(color_hex)

            tag_item = QTreeWidgetItem([display_name, str(t["count"]), ""])
            tag_item.setIcon(0, color_icon)
            tag_item.setData(0, Qt.ItemDataRole.UserRole, tag_name)
            tag_item.setData(0, Qt.ItemDataRole.UserRole + 1, "tag")

            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            tag_item.setFont(0, font)
            tag_item.setForeground(0, QBrush(QColor("#ffffff")))
            tag_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

            self.addTopLevelItem(tag_item)

            if tag_name in expanded_tags:
                tag_item.setExpanded(True)
                self._load_child_notes(tag_item, force_reload=True)
            elif t["count"] > 0:
                dummy = QTreeWidgetItem(["Loading...", "-", ""])
                tag_item.addChild(dummy)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        row_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if row_type == "tag":
            self._load_child_notes(item, force_reload=False)

    def _load_child_notes(self, tag_item: QTreeWidgetItem, force_reload=False):
        tag_name = tag_item.data(0, Qt.ItemDataRole.UserRole)
        if not tag_name:
            return

        is_dummy = (tag_item.childCount() == 1 and tag_item.child(0).text(0) == "Loading...")
        if force_reload or is_dummy:
            tag_item.takeChildren()

            notes = self.cache_manager.get_notes_for_tag(tag_name, filter_query=self.current_filter)
            for n in notes:
                display_title = f"📄 {n['title']}"
                note_item = QTreeWidgetItem([display_title, "-", n["shared_tags_str"]])
                note_item.setData(0, Qt.ItemDataRole.UserRole, n["path"])
                note_item.setData(0, Qt.ItemDataRole.UserRole + 1, "note")

                note_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                note_item.setForeground(2, QBrush(QColor("#a6adc8")))

                tag_item.addChild(note_item)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        row_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if row_type == "note":
            rel_path = item.data(0, Qt.ItemDataRole.UserRole)
            if rel_path:
                self.note_double_clicked.emit(rel_path)
        elif row_type == "tag":
            item.setExpanded(not item.isExpanded())

    def _show_context_menu(self, pos):
        item_at_pos = self.itemAt(pos)
        selected_items = self.selectedItems()

        if item_at_pos and item_at_pos not in selected_items:
            self.clearSelection()
            item_at_pos.setSelected(True)
            selected_items = [item_at_pos]

        if not selected_items and item_at_pos:
            selected_items = [item_at_pos]

        if not selected_items:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #04395e;
                color: #ffffff;
            }
        """)

        tag_items = [it for it in selected_items if it.data(0, Qt.ItemDataRole.UserRole + 1) == "tag"]
        note_items = [it for it in selected_items if it.data(0, Qt.ItemDataRole.UserRole + 1) == "note"]

        # Case 1: Right-clicked a Tag Node
        if len(tag_items) == 1 and not note_items:
            tag_item = tag_items[0]
            tag_name = tag_item.data(0, Qt.ItemDataRole.UserRole)

            act_add = QAction(f"➕ Add tag to notes under '#{tag_name}'...", self)
            act_add.triggered.connect(lambda checked=False, ti=tag_item: self._prompt_add_tag_to_tag_group(ti))
            menu.addAction(act_add)

            act_remove_all = QAction(f"❌ Remove tag '#{tag_name}' from ALL notes in group", self)
            act_remove_all.triggered.connect(lambda checked=False, ti=tag_item: self._remove_tag_from_tag_group(ti))
            menu.addAction(act_remove_all)

        # Case 2: Right-clicked Note Node(s)
        elif note_items:
            note_paths = list(dict.fromkeys(it.data(0, Qt.ItemDataRole.UserRole) for it in note_items if it.data(0, Qt.ItemDataRole.UserRole)))

            act_add = QAction(f"➕ Add Tag to {len(note_paths)} Note(s)...", self)
            act_add.triggered.connect(lambda checked=False, np=note_paths: self._prompt_add_tag_to_notes(np))
            menu.addAction(act_add)

            # Determine parent tag if notes are under tag item
            parents = set()
            for it in note_items:
                parent_it = it.parent()
                if parent_it and parent_it.data(0, Qt.ItemDataRole.UserRole + 1) == "tag":
                    parents.add(parent_it.data(0, Qt.ItemDataRole.UserRole))

            if len(parents) == 1:
                parent_tag_name = list(parents)[0]
                act_remove_parent = QAction(f"❌ Remove tag '#{parent_tag_name}' from selected note(s)", self)
                act_remove_parent.triggered.connect(
                    lambda checked=False, np=note_paths, ptn=parent_tag_name: self._modify_notes_tag(np, ptn, action="remove")
                )
                menu.addAction(act_remove_parent)

            # Submenu to remove specific tags from selected notes
            common_tags = self.cache_manager.get_tags_for_file_paths(note_paths)
            if common_tags:
                remove_menu = menu.addMenu("❌ Remove Specific Tag")
                remove_menu.setStyleSheet(menu.styleSheet())
                for t_name in common_tags:
                    act_rem = QAction(f"#{t_name}", self)
                    act_rem.triggered.connect(
                        lambda checked=False, np=note_paths, tn=t_name: self._modify_notes_tag(np, tn, action="remove")
                    )
                    remove_menu.addAction(act_rem)

            # Action to remove ALL tags from selected note(s)
            act_remove_all_tags = QAction(f"🔥 Remove ALL tags from selected note(s)", self)
            act_remove_all_tags.triggered.connect(
                lambda checked=False, np=note_paths: self._modify_notes_tag(np, "", action="remove_all")
            )
            menu.addAction(act_remove_all_tags)

            menu.addSeparator()

            if len(note_paths) == 1:
                act_open = QAction("📄 Open Note in Editor", self)
                act_open.triggered.connect(lambda checked=False, p=note_paths[0]: self.note_double_clicked.emit(p))
                menu.addAction(act_open)

        menu.exec(self.mapToGlobal(pos))

    def _prompt_add_tag_to_tag_group(self, tag_item: QTreeWidgetItem):
        tag_name = tag_item.data(0, Qt.ItemDataRole.UserRole)
        notes = self.cache_manager.get_notes_for_tag(tag_name, filter_query=self.current_filter)
        note_paths = [n["path"] for n in notes]
        if note_paths:
            self._prompt_add_tag_to_notes(note_paths)

    def _remove_tag_from_tag_group(self, tag_item: QTreeWidgetItem):
        tag_name = tag_item.data(0, Qt.ItemDataRole.UserRole)
        notes = self.cache_manager.get_notes_for_tag(tag_name, filter_query=self.current_filter)
        note_paths = [n["path"] for n in notes]
        if note_paths:
            reply = QMessageBox.question(
                self,
                "Confirm Tag Removal",
                f"Are you sure you want to remove tag '#{tag_name}' from ALL {len(note_paths)} notes in this group?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._modify_notes_tag(note_paths, tag_name, action="remove")

    def _prompt_add_tag_to_notes(self, note_paths: List[str]):
        if not note_paths:
            return
        all_tags = [t["name"] for t in self.cache_manager.get_all_tags()]
        dialog = AddTagDialog(all_tags, target_count=len(note_paths), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_tag = dialog.selected_tag
            if new_tag:
                self._modify_notes_tag(note_paths, new_tag, action="add")

    def _modify_notes_tag(self, rel_paths: List[str], tag_name: str, action: str = "add"):
        if not self.vault_path or not Path(self.vault_path).exists():
            QMessageBox.warning(
                self,
                "Vault Path Error",
                f"Cannot update tag: Vault path is not set or valid.\nPath: '{self.vault_path}'"
            )
            return

        clean_tag = tag_name.lstrip("#").strip()
        if action != "remove_all" and not clean_tag:
            return

        vault_root = Path(self.vault_path).resolve()
        success_count = 0
        error_msgs = []

        for rel_path in rel_paths:
            abs_path = (vault_root / rel_path).resolve()
            if not abs_path.exists():
                error_msgs.append(f"File not found: {abs_path}")
                continue

            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                post = frontmatter.loads(content)
                meta = post.metadata

                tags_val = meta.get("tags", None) or meta.get("tag", None)
                existing_tags = []
                if isinstance(tags_val, str):
                    existing_tags = [t.strip().lstrip("#") for t in re.split(r"[,,\s]+", tags_val) if t.strip()]
                elif isinstance(tags_val, list):
                    existing_tags = [str(t).strip().lstrip("#") for t in tags_val if str(t).strip()]

                if "tag" in meta:
                    del meta["tag"]

                modified = False

                if action == "add":
                    if not any(t.lower() == clean_tag.lower() for t in existing_tags):
                        existing_tags.append(clean_tag)
                        modified = True

                elif action == "remove":
                    new_tags = [t for t in existing_tags if t.lower() != clean_tag.lower()]
                    if len(new_tags) != len(existing_tags):
                        existing_tags = new_tags
                        modified = True

                    # Strip body inline hashtag #clean_tag
                    pattern = re.compile(r'(^|[\s\(\[\{\<"\'`=])#' + re.escape(clean_tag) + r'(?=[\s,\.\?!;\)\]\}>"\'`/:]|$)', re.IGNORECASE)
                    if pattern.search(post.content):
                        post.content = pattern.sub(r'\1', post.content)
                        modified = True

                elif action == "remove_all":
                    if existing_tags:
                        existing_tags = []
                        modified = True

                    # Strip all body hashtags
                    pattern = re.compile(r'(^|[\s\(\[\{\<"\'`=])#[a-zA-Z0-9_\-/]+(?=[\s,\.\?!;\)\]\}>"\'`/:]|$)', re.IGNORECASE)
                    if pattern.search(post.content):
                        post.content = pattern.sub(r'\1', post.content)
                        modified = True

                meta["tags"] = existing_tags
                new_file_content = frontmatter.dumps(post)

                with open(abs_path, "w", encoding="utf-8") as f:
                    f.write(new_file_content)

                updated_note = VaultScanner.scan_file(abs_path, vault_root)
                if updated_note:
                    self.cache_manager.incremental_update_file(updated_note, is_delete=False)

                success_count += 1
            except Exception as e:
                error_msgs.append(f"{rel_path}: {e}")

        if action == "add":
            act_word = f"Added tag '#{clean_tag}'"
        elif action == "remove":
            act_word = f"Removed tag '#{clean_tag}'"
        else:
            act_word = "Removed ALL tags"

        if success_count > 0:
            msg = f"✅ {act_word} on {success_count} note file(s)."
            self.status_message.emit(msg)
            QMessageBox.information(self, "Tag Operation Successful", msg)
            self.tags_updated.emit()
            self.reload_tags(filter_query=self.current_filter, sort_by=self.sort_order, show_empty=self.show_empty, show_orphans=self.show_orphans)
        elif error_msgs:
            QMessageBox.critical(self, "Tag Operation Error", f"Failed to modify notes:\n" + "\n".join(error_msgs))
        else:
            QMessageBox.warning(self, "No Changes", f"Note file(s) did not contain tag '#{clean_tag}'.")

    def flash_note_saved(self, rel_path: str):
        """
        Flashes the note row briefly green as a visual confirmation after saving.
        Safe against Qt C++ widget deletion.
        """
        for i in range(self.topLevelItemCount()):
            tag_item = self.topLevelItem(i)
            for c in range(tag_item.childCount()):
                child = tag_item.child(c)
                if child.data(0, Qt.ItemDataRole.UserRole) == rel_path:
                    child.setBackground(0, QBrush(QColor("#2ecc71")))
                    child.setBackground(1, QBrush(QColor("#2ecc71")))
                    child.setBackground(2, QBrush(QColor("#2ecc71")))
                    child.setForeground(0, QBrush(QColor("#11111b")))

                    QTimer.singleShot(800, lambda item=child: self._reset_item_background(item))

    def _reset_item_background(self, item: QTreeWidgetItem):
        try:
            item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
            item.setBackground(1, QBrush(Qt.GlobalColor.transparent))
            item.setBackground(2, QBrush(Qt.GlobalColor.transparent))
            item.setForeground(0, QBrush(QColor("#d4d4d4")))
        except (RuntimeError, AttributeError, Exception):
            pass
