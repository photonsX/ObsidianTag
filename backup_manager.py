import os
import zipfile
from datetime import datetime
from pathlib import Path

class BackupManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    @property
    def vault_path(self) -> Path:
        v = self.config_manager.get("vault_path")
        return Path(v) if v else None

    @property
    def backup_path(self) -> Path:
        b = self.config_manager.get("backup_path")
        return Path(b) if b else None

    @property
    def max_backups(self) -> int:
        return int(self.config_manager.get("max_backups", 10))

    @property
    def auto_delete_oldest(self) -> bool:
        return bool(self.config_manager.get("auto_delete_oldest", True))

    def list_backups(self) -> list:
        if not self.backup_path or not self.backup_path.exists():
            return []
        
        backups = []
        for file in self.backup_path.glob("*.zip"):
            try:
                st = file.stat()
                backups.append({
                    "filename": file.name,
                    "path": str(file),
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "mtime": st.st_mtime,
                    "created_at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
            except Exception:
                pass
        
        backups.sort(key=lambda b: b["mtime"], reverse=True)
        return backups

    def create_backup(self) -> tuple[bool, str]:
        if not self.vault_path or not self.vault_path.exists():
            return False, "Vault path is not set or does not exist."

        if not self.backup_path:
            return False, "Backup folder path is not set."

        try:
            self.backup_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            vault_name = self.vault_path.name or "ObsidianVault"
            zip_filename = f"{vault_name}_backup_{timestamp}.zip"
            zip_filepath = self.backup_path / zip_filename

            ignored_folders = set(self.config_manager.get("ignored_folders", [".obsidian", ".git", ".trash"]))

            note_count = 0
            with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.vault_path):
                    dirs[:] = [d for d in dirs if d not in ignored_folders and not d.startswith(".")]
                    for file in files:
                        abs_file = Path(root) / file
                        rel_file = abs_file.relative_to(self.vault_path)
                        zipf.write(abs_file, arcname=rel_file)
                        if file.endswith(".md"):
                            note_count += 1

            pruned_count = self.enforce_max_backups()

            msg = f"Backup created successfully: {zip_filename} ({note_count} notes)."
            if pruned_count > 0:
                msg += f"\nAuto-deleted {pruned_count} oldest backup(s) (Max limit: {self.max_backups})."

            return True, msg

        except Exception as e:
            return False, f"Failed to create backup: {str(e)}"

    def enforce_max_backups(self) -> int:
        if not self.auto_delete_oldest:
            return 0

        backups = self.list_backups()
        max_b = self.max_backups
        pruned = 0
        if len(backups) > max_b:
            to_delete = backups[max_b:]
            for b in to_delete:
                try:
                    Path(b["path"]).unlink()
                    pruned += 1
                except Exception as e:
                    print(f"Error deleting old backup {b['path']}: {e}")
        return pruned
