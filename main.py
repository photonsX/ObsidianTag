import sys
import os
import csv
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QFileDialog, QMessageBox, QProgressBar, QLabel,
    QStatusBar, QDialog, QFormLayout, QPushButton, QMenu
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QAction

from config_manager import ConfigManager
from color_manager import ColorManager
from cache_manager import CacheManager
from vault_scanner import VaultScanner, VaultScanWorker
from file_watcher import FileWatcherThread
from search_bar import SearchBar
from table_widget import TagTableWidget
from note_editor import NoteEditorPanel
from settings_dialog import SettingsDialog

class TagStatsDialog(QDialog):
    def __init__(self, stats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Obsidian Tag Statistics")
        self.setFixedSize(360, 240)
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #d4d4d4;
            }
            QLabel {
                font-size: 13px;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #0e639c;
                color: #ffffff;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        form.addRow("Total Unique Tags:", QLabel(f"<b>{stats.total_tags}</b>"))
        form.addRow("Total Indexed Notes:", QLabel(f"<b>{stats.total_notes}</b>"))
        form.addRow("Most Used Tag:", QLabel(f"<b style='color:#007acc;'>{stats.most_used_tag}</b> ({stats.most_used_count} notes)"))
        form.addRow("Orphan Tags (1 note):", QLabel(f"<b style='color:#e67e22;'>{stats.orphan_tags_count}</b>"))
        form.addRow("Avg Tags per Note:", QLabel(f"<b>{stats.avg_tags_per_note}</b>"))

        layout.addLayout(form)
        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignCenter)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Obsidian Tag Viewer & Editor")
        self.resize(1100, 750)

        self.config_manager = ConfigManager()
        self.cache_manager = CacheManager()
        self.watcher_thread = None
        self.scan_worker = None

        self.setup_ui()
        self.setup_menu()
        self.apply_theme()

        # Restore window geometry if saved
        geom = self.config_manager.get("window_geometry")
        if geom:
            try:
                self.restoreGeometry(bytes.fromhex(geom))
            except Exception:
                pass

        # Check vault path on startup
        vault_p = self.config_manager.get("vault_path")
        if vault_p and Path(vault_p).exists():
            self.start_vault_scan(vault_p)
            self.start_file_watcher(vault_p)
        else:
            QTimer.singleShot(500, self.open_settings_dialog)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Search & Settings Header Row
        header_row = QHBoxLayout()
        self.search_bar = SearchBar()
        self.search_bar.search_changed.connect(self._on_search_changed)
        header_row.addWidget(self.search_bar, stretch=1)

        btn_settings = QPushButton("⚙️ Settings")
        btn_settings.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                padding: 5px 14px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3c3c3c;
                color: #ffffff;
            }
        """)
        btn_settings.clicked.connect(self.open_settings_dialog)
        header_row.addWidget(btn_settings)

        main_layout.addLayout(header_row)

        # 2. Main Vertical Splitter (Table on top, Editor below)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Upper Pane: Tag Table Widget
        self.table_widget = TagTableWidget(self.cache_manager)
        self.table_widget.note_double_clicked.connect(self.open_note_editor)
        self.splitter.addWidget(self.table_widget)

        # Lower Pane: Inline Note Editor Panel
        editor_font_sz = self.config_manager.get("editor_font_size", 13)
        self.editor_panel = NoteEditorPanel(font_size=editor_font_sz)
        self.editor_panel.save_requested.connect(self.save_note_changes)
        self.editor_panel.cancel_requested.connect(self.close_note_editor)
        self.editor_panel.hide()  # Hidden by default until double-clicked
        self.splitter.addWidget(self.editor_panel)

        self.splitter.setSizes([500, 300])
        main_layout.addWidget(self.splitter, stretch=1)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_status_info = QLabel("Ready")
        self.status_bar.addWidget(self.lbl_status_info, stretch=1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(180)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        self.status_bar.addPermanentWidget(self.progress_bar)

    def setup_menu(self):
        menubar = self.menuBar()

        # --- File Menu ---
        file_menu = menubar.addMenu("File")
        
        act_settings = QAction("Settings...", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(act_settings)

        act_refresh = QAction("Refresh Cache (Full Rescan)", self)
        act_refresh.setShortcut("F5")
        act_refresh.triggered.connect(self.refresh_vault_cache)
        file_menu.addAction(act_refresh)

        act_export_csv = QAction("Export to CSV", self)
        act_export_csv.triggered.connect(self.export_to_csv)
        file_menu.addAction(act_export_csv)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # --- View Menu ---
        view_menu = menubar.addMenu("View")

        sort_menu = view_menu.addMenu("Sort by")
        act_sort_count = QAction("Count (Highest First)", self)
        act_sort_count.triggered.connect(lambda: self.set_sort_order("count_desc"))
        act_sort_alpha = QAction("Alphabetical (A-Z)", self)
        act_sort_alpha.triggered.connect(lambda: self.set_sort_order("alphabetical"))
        act_sort_mod = QAction("Last Modified", self)
        act_sort_mod.triggered.connect(lambda: self.set_sort_order("modified_desc"))

        sort_menu.addAction(act_sort_count)
        sort_menu.addAction(act_sort_alpha)
        sort_menu.addAction(act_sort_mod)

        view_menu.addSeparator()

        act_collapse = QAction("Collapse All", self)
        act_collapse.triggered.connect(self.table_widget.collapseAll)
        view_menu.addAction(act_collapse)

        # --- Help Menu ---
        help_menu = menubar.addMenu("Help")

        act_stats = QAction("Tag Statistics", self)
        act_stats.triggered.connect(self.show_tag_stats)
        help_menu.addAction(act_stats)

        act_about = QAction("About", self)
        act_about.triggered.connect(self.show_about_dialog)
        help_menu.addAction(act_about)

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QMenuBar {
                background-color: #252526;
                color: #d4d4d4;
                border-bottom: 1px solid #3c3c3c;
            }
            QMenuBar::item:selected {
                background-color: #3c3c3c;
                color: #ffffff;
            }
            QMenu {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QMenu::item:selected {
                background-color: #04395e;
                color: #ffffff;
            }
            QStatusBar {
                background-color: #007acc;
                color: #ffffff;
                font-weight: 500;
            }
            QStatusBar QLabel {
                color: #ffffff;
            }
        """)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config_manager, self, on_vault_changed=self._on_vault_changed_from_settings)
        dialog.exec()

    def _on_vault_changed_from_settings(self, new_vault_path: str):
        if new_vault_path and Path(new_vault_path).exists():
            self.start_vault_scan(new_vault_path)
            self.start_file_watcher(new_vault_path)

    def start_vault_scan(self, vault_path: str):
        self.lbl_status_info.setText("Scanning vault...")
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.scan_worker = VaultScanWorker(vault_path)
        self.scan_worker.progress.connect(self._on_scan_progress)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.error.connect(self._on_scan_error)
        self.scan_worker.start()

    def _on_scan_progress(self, current: int, total: int, file_name: str):
        if total > 0:
            val = int((current / total) * 100)
            self.progress_bar.setValue(val)
        self.lbl_status_info.setText(f"Scanning ({current}/{total}): {file_name}")

    def _on_scan_finished(self, notes_list: list):
        self.progress_bar.hide()
        self.cache_manager.full_scan_update(notes_list)
        
        sort_order = self.config_manager.get("sort_order", "count_desc")
        self.table_widget.reload_tags(filter_query=self.search_bar.text(), sort_by=sort_order)
        
        stats = self.cache_manager.get_tag_stats()
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.lbl_status_info.setText(
            f"{stats.total_tags} tags loaded | {stats.total_notes} notes indexed | Last scan: {timestamp}"
        )

    def _on_scan_error(self, err_msg: str):
        self.progress_bar.hide()
        self.lbl_status_info.setText(f"Scan error: {err_msg}")
        QMessageBox.critical(self, "Vault Scan Error", err_msg)

    def refresh_vault_cache(self):
        vault_p = self.config_manager.get("vault_path")
        if vault_p:
            self.start_vault_scan(vault_p)

    def start_file_watcher(self, vault_path: str):
        if self.watcher_thread:
            self.watcher_thread.stop()
            self.watcher_thread.wait()

        self.watcher_thread = FileWatcherThread(vault_path)
        self.watcher_thread.file_changed.connect(self._on_file_changed)
        self.watcher_thread.status_message.connect(lambda msg: self.lbl_status_info.setText(msg))
        self.watcher_thread.start()

    def _on_file_changed(self, abs_path_str: str, event_type: str):
        vault_p = Path(self.config_manager.get("vault_path"))
        abs_p = Path(abs_path_str)

        if event_type == "deleted":
            rel_p = str(abs_p.relative_to(vault_p)).replace("\\", "/")
            dummy_note = Note(path=rel_p)
            self.cache_manager.incremental_update_file(dummy_note, is_delete=True)
        else:
            note = VaultScanner.scan_file(abs_p, vault_p)
            if note:
                self.cache_manager.incremental_update_file(note, is_delete=False)

        sort_order = self.config_manager.get("sort_order", "count_desc")
        self.table_widget.reload_tags(filter_query=self.search_bar.text(), sort_by=sort_order)

        stats = self.cache_manager.get_tag_stats()
        self.lbl_status_info.setText(f"Vault updated incrementally | {stats.total_tags} tags | {stats.total_notes} notes")

    def _on_search_changed(self, query: str):
        sort_order = self.config_manager.get("sort_order", "count_desc")
        self.table_widget.reload_tags(filter_query=query, sort_by=sort_order)

    def set_sort_order(self, sort_order: str):
        self.config_manager.set("sort_order", sort_order)
        self.table_widget.reload_tags(filter_query=self.search_bar.text(), sort_by=sort_order)

    def open_note_editor(self, rel_path: str):
        vault_p = Path(self.config_manager.get("vault_path"))
        abs_p = vault_p / rel_path

        if not abs_p.exists():
            QMessageBox.warning(self, "File Not Found", f"Note file does not exist: {rel_path}")
            return

        try:
            with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            all_tags = [t["name"] for t in self.cache_manager.get_all_tags()]
            self.editor_panel.load_note(rel_path, content, available_tags=all_tags)
            self.editor_panel.show()
            self.splitter.setSizes([350, 400])
        except Exception as e:
            QMessageBox.critical(self, "Error Reading Note", f"Could not read file: {e}")

    def close_note_editor(self):
        self.editor_panel.hide()

    def save_note_changes(self, rel_path: str, new_content: str):
        vault_p = Path(self.config_manager.get("vault_path"))
        abs_p = vault_p / rel_path

        try:
            with open(abs_p, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Update cache incrementally
            note = VaultScanner.scan_file(abs_p, vault_p)
            if note:
                self.cache_manager.incremental_update_file(note, is_delete=False)

            self.close_note_editor()

            # Reload tree view and flash note row green as confirmation
            sort_order = self.config_manager.get("sort_order", "count_desc")
            self.table_widget.reload_tags(filter_query=self.search_bar.text(), sort_by=sort_order)
            self.table_widget.flash_note_saved(rel_path)

            self.lbl_status_info.setText(f"Saved changes to {rel_path}")

        except Exception as e:
            QMessageBox.critical(self, "Save Permission Error", f"Failed to save note to disk: {e}")

    def export_to_csv(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Tags View to CSV", "obsidian_tags_export.csv", "CSV Files (*.csv)")
        if filename:
            try:
                tags = self.cache_manager.get_all_tags(
                    sort_by=self.config_manager.get("sort_order", "count_desc"),
                    filter_query=self.search_bar.text()
                )
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Tag Name", "Note Count", "Matching Notes", "Co-Occurring Shared Tags"])

                    for t in tags:
                        notes = self.cache_manager.get_notes_for_tag(t["name"])
                        for n in notes:
                            writer.writerow([f"#{t['name']}", t["count"], n["title"], n["shared_tags_str"]])

                QMessageBox.information(self, "Export Complete", f"Successfully exported view to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {e}")

    def show_tag_stats(self):
        stats = self.cache_manager.get_tag_stats()
        dialog = TagStatsDialog(stats, self)
        dialog.exec()

    def show_about_dialog(self):
        QMessageBox.about(
            self,
            "About Obsidian Tag Viewer & Editor",
            "<h3>Obsidian Tag Viewer & Editor</h3>"
            "<p>A native Python (PyQt6) desktop application for viewing, searching, "
            "and inline editing tags and notes in your Obsidian vault.</p>"
            "<p><b>Version:</b> 1.0.0<br><b>Engine:</b> SQLite3 + Watchdog</p>"
        )

    def closeEvent(self, event):
        # Save geometry
        geom_hex = self.saveGeometry().toHex().data().decode("ascii")
        self.config_manager.set("window_geometry", geom_hex)

        if self.watcher_thread:
            self.watcher_thread.stop()
            self.watcher_thread.wait()

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
