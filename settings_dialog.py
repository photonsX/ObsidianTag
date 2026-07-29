from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QCheckBox, QFileDialog, QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt
from backup_manager import BackupManager

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None, on_vault_changed=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.backup_manager = BackupManager(self.config_manager)
        self.on_vault_changed = on_vault_changed

        self.setWindowTitle("Application & Backup Settings")
        self.setFixedSize(540, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QGroupBox {
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #007acc;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                font-size: 13px;
                color: #d4d4d4;
            }
            QLineEdit, QSpinBox {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 5px 8px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1px solid #007acc;
            }
            QPushButton {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3c3c3c;
            }
            QPushButton#saveBtn {
                background-color: #0e639c;
                border: none;
                font-weight: bold;
            }
            QPushButton#saveBtn:hover {
                background-color: #1177bb;
            }
            QPushButton#backupBtn {
                background-color: #2ecc71;
                color: #11111b;
                border: none;
                font-weight: bold;
            }
            QPushButton#backupBtn:hover {
                background-color: #27ae60;
            }
            QCheckBox {
                color: #d4d4d4;
                font-size: 13px;
            }
        """)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Location of Vault Group
        grp_vault = QGroupBox("Obsidian Vault Location")
        f_v = QVBoxLayout(grp_vault)
        
        row_v = QHBoxLayout()
        self.txt_vault = QLineEdit()
        self.txt_vault.setPlaceholderText("Select your Obsidian Vault directory...")
        btn_browse_v = QPushButton("Browse...")
        btn_browse_v.clicked.connect(self.browse_vault)
        row_v.addWidget(self.txt_vault)
        row_v.addWidget(btn_browse_v)
        f_v.addLayout(row_v)
        main_layout.addWidget(grp_vault)

        # 2. Location of Backup & Controls Group
        grp_backup = QGroupBox("Vault Backup Preferences")
        f_b = QFormLayout(grp_backup)
        f_b.setSpacing(10)

        row_b = QHBoxLayout()
        self.txt_backup = QLineEdit()
        self.txt_backup.setPlaceholderText("Select backup destination folder...")
        btn_browse_b = QPushButton("Browse...")
        btn_browse_b.clicked.connect(self.browse_backup)
        row_b.addWidget(self.txt_backup)
        row_b.addWidget(btn_browse_b)
        f_b.addRow("Backup Location:", row_b)

        self.spin_max = QSpinBox()
        self.spin_max.setRange(1, 100)
        self.spin_max.setValue(10)
        self.spin_max.setFixedWidth(80)
        f_b.addRow("Max No. of Backups:", self.spin_max)

        self.chk_auto_del = QCheckBox("Auto-delete oldest backup when limit is reached")
        f_b.addRow("", self.chk_auto_del)

        btn_backup_now = QPushButton("📦 Backup Vault Now")
        btn_backup_now.setObjectName("backupBtn")
        btn_backup_now.clicked.connect(self.run_backup_now)
        f_b.addRow("", btn_backup_now)

        main_layout.addWidget(grp_backup)

        # Actions
        row_actions = QHBoxLayout()
        row_actions.addStretch()

        btn_save = QPushButton("Save Settings")
        btn_save.setObjectName("saveBtn")
        btn_save.clicked.connect(self.save_settings)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        row_actions.addWidget(btn_save)
        row_actions.addWidget(btn_cancel)
        main_layout.addLayout(row_actions)

    def load_settings(self):
        self.txt_vault.setText(self.config_manager.get("vault_path", ""))
        self.txt_backup.setText(self.config_manager.get("backup_path", ""))
        self.spin_max.setValue(int(self.config_manager.get("max_backups", 10)))
        self.chk_auto_del.setChecked(bool(self.config_manager.get("auto_delete_oldest", True)))

    def browse_vault(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Obsidian Vault Directory")
        if folder:
            self.txt_vault.setText(folder)

    def browse_backup(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Directory")
        if folder:
            self.txt_backup.setText(folder)

    def run_backup_now(self):
        # Temporarily set config values for backup manager execution
        self.config_manager.set("vault_path", self.txt_vault.text().strip())
        self.config_manager.set("backup_path", self.txt_backup.text().strip())
        self.config_manager.set("max_backups", self.spin_max.value())
        self.config_manager.set("auto_delete_oldest", self.chk_auto_del.isChecked())

        success, message = self.backup_manager.create_backup()
        if success:
            QMessageBox.information(self, "Backup Complete", message)
        else:
            QMessageBox.warning(self, "Backup Failed", message)

    def save_settings(self):
        old_vault = self.config_manager.get("vault_path")
        new_vault = self.txt_vault.text().strip()

        self.config_manager.set("vault_path", new_vault)
        self.config_manager.set("backup_path", self.txt_backup.text().strip())
        self.config_manager.set("max_backups", self.spin_max.value())
        self.config_manager.set("auto_delete_oldest", self.chk_auto_del.isChecked())

        QMessageBox.information(self, "Settings Saved", "Preferences saved to config.json.")

        if self.on_vault_changed and old_vault != new_vault:
            self.on_vault_changed(new_vault)

        self.accept()
