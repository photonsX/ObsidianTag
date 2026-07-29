import time
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QBrush

from color_manager import ColorManager
from cache_manager import CacheManager

class TagTableWidget(QTreeWidget):
    note_double_clicked = pyqtSignal(str)  # rel_path
    status_message = pyqtSignal(str)

    def __init__(self, cache_manager: CacheManager, parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.current_filter = ""
        self.sort_order = "count_desc"
        self.show_empty = False
        self.show_orphans = True

        self.init_ui()

    def init_ui(self):
        self.setColumnCount(3)
        self.setHeaderLabels(["TAG / NOTE", "COUNT", "SHARED TAGS"])

        # Column width behavior
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 320)
        self.setColumnWidth(1, 80)

        self.setAnimated(True)
        self.setIndentation(20)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)

        # Style matching Obsidian dark theme
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

        # Remember currently expanded tag names
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

            # Style tag row
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            tag_item.setFont(0, font)
            tag_item.setForeground(0, QBrush(QColor("#ffffff")))
            tag_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

            self.addTopLevelItem(tag_item)

            if tag_name in expanded_tags:
                tag_item.setExpanded(True)
                self._load_child_notes(tag_item, force_reload=True)
            elif t["count"] > 0:
                # Add dummy child for unexpanded lazy loading
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

        # Reload if forced or currently showing dummy loader
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
                    # Flash green
                    child.setBackground(0, QBrush(QColor("#2ecc71")))
                    child.setBackground(1, QBrush(QColor("#2ecc71")))
                    child.setBackground(2, QBrush(QColor("#2ecc71")))
                    child.setForeground(0, QBrush(QColor("#11111b")))

                    # Reset back after 800ms safely
                    QTimer.singleShot(800, lambda item=child: self._reset_item_background(item))

    def _reset_item_background(self, item: QTreeWidgetItem):
        try:
            item.setBackground(0, QBrush(Qt.GlobalColor.transparent))
            item.setBackground(1, QBrush(Qt.GlobalColor.transparent))
            item.setBackground(2, QBrush(Qt.GlobalColor.transparent))
            item.setForeground(0, QBrush(QColor("#d4d4d4")))
        except (RuntimeError, AttributeError, Exception):
            pass
