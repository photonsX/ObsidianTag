import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QLineEdit,
    QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QFrame,
    QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QFont

from cache_manager import CacheManager
from note_editor import NoteEditorPanel


class ActivityGraphWidget(QFrame):
    """Simple activity distribution bar chart rendered using QPainter."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
            }
        """)
        self.activity_data: Dict[str, int] = {}  # "YYYY-MM-DD" -> count

    def set_data(self, data: Dict[str, int]):
        self.activity_data = data
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.activity_data:
            painter.setPen(QColor("#666666"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No activity data available in selected range")
            return

        sorted_keys = sorted(self.activity_data.keys())
        max_val = max(self.activity_data.values()) if self.activity_data else 1

        width = self.width() - 20
        height = self.height() - 20
        start_x = 10
        bottom_y = self.height() - 10

        num_bars = len(sorted_keys)
        bar_width = max(2, min(24, (width - (num_bars * 2)) // max(1, num_bars)))
        spacing = 2

        for i, date_str in enumerate(sorted_keys):
            val = self.activity_data[date_str]
            bar_height = max(4, int((val / max_val) * (height - 15)))
            x = start_x + i * (bar_width + spacing)
            y = bottom_y - bar_height

            if x + bar_width > self.width() - 10:
                break

            # Color intensity based on activity value
            intensity = min(255, 100 + int((val / max_val) * 155))
            bar_color = QColor(0, int(122 * (val / max_val) + 120), intensity)

            painter.setBrush(QBrush(bar_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(x, y, bar_width, bar_height, 2, 2)

        # Label max value
        painter.setPen(QColor("#888888"))
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.drawText(self.width() - 120, 18, f"Peak: {max_val} notes")


class TemporalViewWidget(QWidget):
    note_saved = pyqtSignal(str)  # Emitted when a note is saved in embedded editor

    def __init__(self, cache_manager: CacheManager, vault_path: str = "", parent=None):
        super().__init__(parent)
        self.cache_manager = cache_manager
        self.vault_path = vault_path
        self.active_mode = "notes"  # "notes" or "tags"
        self.current_start_ts: Optional[float] = None
        self.current_end_ts: Optional[float] = None

        self.setup_ui()
        self.load_data()

    def set_vault_path(self, path: str):
        self.vault_path = path
        self.editor_panel.set_vault_path(path)
        self.load_data()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # --- 1. Controls Header ---
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 4px;
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
            }
            QComboBox {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #0e639c;
                color: #ffffff;
                border-color: #007acc;
            }
        """)

        header_layout = QVBoxLayout(header_frame)
        header_layout.setSpacing(6)

        # Row 1: Mode Switcher & Search
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        lbl_mode = QLabel("Mode:")
        self.btn_notes_mode = QPushButton("📝 Notes Timeline")
        self.btn_notes_mode.setCheckable(True)
        self.btn_notes_mode.setChecked(True)
        self.btn_notes_mode.clicked.connect(lambda: self.switch_mode("notes"))

        self.btn_tags_mode = QPushButton("🏷️ Tag Analytics")
        self.btn_tags_mode.setCheckable(True)
        self.btn_tags_mode.clicked.connect(lambda: self.switch_mode("tags"))

        row1.addWidget(lbl_mode)
        row1.addWidget(self.btn_notes_mode)
        row1.addWidget(self.btn_tags_mode)

        row1.addSpacing(15)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter timeline notes or tags...")
        self.search_input.textChanged.connect(self.load_data)
        row1.addWidget(self.search_input, stretch=1)

        header_layout.addLayout(row1)

        # Row 2: Date Presets & Sorting & Granularity
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        lbl_range = QLabel("Time Filter:")
        row2.addWidget(lbl_range)

        self.combo_presets = QComboBox()
        self.combo_presets.addItems([
            "All Time",
            "Last 7 Days",
            "Last 30 Days",
            "Last 90 Days",
            "This Year"
        ])
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        row2.addWidget(self.combo_presets)

        row2.addSpacing(10)

        lbl_gran = QLabel("Grouping:")
        self.combo_granularity = QComboBox()
        self.combo_granularity.addItems(["Daily", "Weekly", "Monthly", "Yearly"])
        self.combo_granularity.setCurrentIndex(0)
        self.combo_granularity.currentIndexChanged.connect(self.load_data)
        row2.addWidget(lbl_gran)
        row2.addWidget(self.combo_granularity)

        row2.addSpacing(10)

        lbl_sort = QLabel("Sort:")
        self.combo_sort = QComboBox()
        self.combo_sort.addItems([
            "Modified (Newest First)",
            "Modified (Oldest First)",
            "Created (Newest First)",
            "Created (Oldest First)"
        ])
        self.combo_sort.currentIndexChanged.connect(self.load_data)
        row2.addWidget(lbl_sort)
        row2.addWidget(self.combo_sort)

        row2.addStretch()

        header_layout.addLayout(row2)
        main_layout.addWidget(header_frame)

        # --- 2. Activity Graph ---
        self.graph_widget = ActivityGraphWidget()
        main_layout.addWidget(self.graph_widget)

        # --- 3. Splitter Workspace (Tree + Embedded Editor) ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Tree widget for timeline
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Timeline Item / Date", "Details", "Tags"])
        self.tree_widget.setColumnWidth(0, 320)
        self.tree_widget.setColumnWidth(1, 160)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #2d2d2d;
                border-radius: 6px;
                font-size: 13px;
            }
            QTreeWidget::item {
                padding: 4px;
                border-bottom: 1px solid #252526;
            }
            QTreeWidget::item:selected {
                background-color: #04395e;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #cccccc;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """)
        self.tree_widget.itemSelectionChanged.connect(self._on_item_selected)
        self.splitter.addWidget(self.tree_widget)

        # Right Pane: Embedded Editor
        self.editor_panel = NoteEditorPanel(vault_path=self.vault_path)
        self.editor_panel.note_saved.connect(self._on_note_saved)
        self.splitter.addWidget(self.editor_panel)

        # Set initial splitter proportions (45/55)
        self.splitter.setSizes([450, 550])
        main_layout.addWidget(self.splitter, stretch=1)

    def switch_mode(self, mode: str):
        self.active_mode = mode
        self.btn_notes_mode.setChecked(mode == "notes")
        self.btn_tags_mode.setChecked(mode == "tags")

        if mode == "notes":
            self.tree_widget.setHeaderLabels(["Timeline Note / Date", "Timestamp", "Tags"])
        else:
            self.tree_widget.setHeaderLabels(["Tag Name", "First Seen / Last Active", "Note Counts"])

        self.load_data()

    def _on_preset_changed(self, index: int):
        now = datetime.now()
        if index == 0:  # All Time
            self.current_start_ts = None
            self.current_end_ts = None
        elif index == 1:  # Last 7 Days
            start = now - timedelta(days=7)
            self.current_start_ts = start.timestamp()
            self.current_end_ts = None
        elif index == 2:  # Last 30 Days
            start = now - timedelta(days=30)
            self.current_start_ts = start.timestamp()
            self.current_end_ts = None
        elif index == 3:  # Last 90 Days
            start = now - timedelta(days=90)
            self.current_start_ts = start.timestamp()
            self.current_end_ts = None
        elif index == 4:  # This Year
            start = datetime(now.year, 1, 1)
            self.current_start_ts = start.timestamp()
            self.current_end_ts = None

        self.load_data()

    def load_data(self):
        query = self.search_input.text().strip()
        sort_text = self.combo_sort.currentText()

        sort_key = "modified_desc"
        if "Oldest First" in sort_text and "Modified" in sort_text:
            sort_key = "modified_asc"
        elif "Newest First" in sort_text and "Created" in sort_text:
            sort_key = "created_desc"
        elif "Oldest First" in sort_text and "Created" in sort_text:
            sort_key = "created_asc"

        granularity = self.combo_granularity.currentText().lower()

        # 1. Update Graph
        act_data = self.cache_manager.get_daily_activity_counts(self.current_start_ts, self.current_end_ts)
        self.graph_widget.set_data(act_data)

        # 2. Update Tree
        self.tree_widget.clear()

        if self.active_mode == "notes":
            notes = self.cache_manager.get_timeline_notes(
                start_ts=self.current_start_ts,
                end_ts=self.current_end_ts,
                sort_by=sort_key,
                filter_query=query
            )
            self._populate_notes_tree(notes, granularity)
        else:
            tag_stats = self.cache_manager.get_tag_timeline_stats(
                start_ts=self.current_start_ts,
                end_ts=self.current_end_ts,
                filter_query=query
            )
            self._populate_tags_tree(tag_stats)

    def _populate_notes_tree(self, notes: List[dict], granularity: str):
        groups: Dict[str, List[dict]] = {}

        for n in notes:
            ts = n["modified_at"] if "modified" in self.combo_sort.currentText().lower() else n["created_at"]
            if ts <= 0:
                bucket = "Unknown Date"
            else:
                dt = datetime.fromtimestamp(ts)
                if granularity == "daily":
                    bucket = dt.strftime("%Y-%m-%d (%A)")
                elif granularity == "weekly":
                    bucket = f"Week {dt.isocalendar()[1]}, {dt.year}"
                elif granularity == "monthly":
                    bucket = dt.strftime("%B %Y")
                else:  # yearly
                    bucket = dt.strftime("%Y")

            if bucket not in groups:
                groups[bucket] = []
            groups[bucket].append(n)

        for bucket_name, group_notes in groups.items():
            parent_item = QTreeWidgetItem(self.tree_widget)
            parent_item.setText(0, f"📅 {bucket_name}")
            parent_item.setText(1, f"{len(group_notes)} note{'s' if len(group_notes) > 1 else ''}")
            parent_item.setForeground(0, QColor("#007acc"))
            font = parent_item.font(0)
            font.setBold(True)
            parent_item.setFont(0, font)

            for n in group_notes:
                child = QTreeWidgetItem(parent_item)
                child.setText(0, f"📄 {n['title']}")
                child.setData(0, Qt.ItemDataRole.UserRole, n["path"])

                mod_dt = datetime.fromtimestamp(n["modified_at"]).strftime("%m/%d %H:%M") if n["modified_at"] > 0 else "N/A"
                child.setText(1, mod_dt)

                tags_str = ", ".join(n["tags"]) if n["tags"] else "[No Tags]"
                child.setText(2, tags_str)
                child.setForeground(2, QColor("#888888"))

            parent_item.setExpanded(True)

    def _populate_tags_tree(self, tag_stats: List[dict]):
        for t in tag_stats:
            item = QTreeWidgetItem(self.tree_widget)
            item.setText(0, f"🏷️ #{t['name']}")
            item.setForeground(0, QColor("#e67e22"))

            first_str = datetime.fromtimestamp(t['first_seen']).strftime("%Y-%m-%d") if t['first_seen'] > 0 else "N/A"
            last_str = datetime.fromtimestamp(t['last_active']).strftime("%Y-%m-%d") if t['last_active'] > 0 else "N/A"
            item.setText(1, f"First: {first_str} | Last: {last_str}")

            item.setText(2, f"{t['range_count']} active ({t['total_count']} total)")

    def _on_item_selected(self):
        selected = self.tree_widget.selectedItems()
        if not selected:
            return
        item = selected[0]
        rel_path = item.data(0, Qt.ItemDataRole.UserRole)
        if rel_path:
            self.editor_panel.open_note(rel_path)

    def _on_note_saved(self, rel_path: str):
        self.load_data()
        self.note_saved.emit(rel_path)
