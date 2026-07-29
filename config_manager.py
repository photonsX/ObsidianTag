import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".obsidian-tag-viewer"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "vault_path": "",
    "backup_path": "",
    "max_backups": 10,
    "auto_delete_oldest": True,
    "window_geometry": "",
    "sort_order": "count_desc",  # "count_desc", "alphabetical", "modified_desc"
    "show_empty_tags": False,
    "show_orphan_tags": True,
    "theme": "dark",
    "editor_font_size": 13,
    "auto_refresh_on_startup": True
}

class ConfigManager:
    def __init__(self, config_path=CONFIG_FILE):
        self.config_path = Path(config_path)
        self.config_dir = self.config_path.parent
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config = self.load_config()

    def load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    return merged
            except Exception as e:
                print(f"Error loading config from {self.config_path}: {e}")
        return DEFAULT_CONFIG.copy()

    def save_config(self) -> bool:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config to {self.config_path}: {e}")
            return False

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()
