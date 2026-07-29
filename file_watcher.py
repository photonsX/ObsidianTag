import time
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QObject
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class VaultWatchdogHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self.callback(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self.callback(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self.callback(event.src_path, "deleted")


class FileWatcherThread(QThread):
    file_changed = pyqtSignal(str, str)  # abs_path, event_type
    status_message = pyqtSignal(str)

    def __init__(self, vault_path: str, debounce_ms=500):
        super().__init__()
        self.vault_path = Path(vault_path)
        self.debounce_ms = debounce_ms
        self.observer = None
        self.pending_events = {}  # abs_path -> (event_type, timestamp)
        self.is_running = True

    def run(self):
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            return

        handler = VaultWatchdogHandler(self._handle_raw_event)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.vault_path), recursive=True)
        self.observer.start()

        self.status_message.emit("File watcher active.")

        try:
            while self.is_running and self.observer.is_alive():
                self._process_debounced_events()
                time.sleep(0.1)
        except Exception as e:
            print(f"File watcher thread exception: {e}")
        finally:
            if self.observer:
                self.observer.stop()
                self.observer.join()

    def _handle_raw_event(self, abs_path: str, event_type: str):
        now = time.time()
        self.pending_events[abs_path] = (event_type, now)
        self.status_message.emit("Vault changed, refreshing...")

    def _process_debounced_events(self):
        now = time.time()
        debounce_sec = self.debounce_ms / 1000.0
        ready_paths = []

        for abs_path, (event_type, ts) in list(self.pending_events.items()):
            if (now - ts) >= debounce_sec:
                ready_paths.append((abs_path, event_type))

        for abs_path, event_type in ready_paths:
            self.pending_events.pop(abs_path, None)
            self.file_changed.emit(abs_path, event_type)

    def stop(self):
        self.is_running = False
        if self.observer:
            self.observer.stop()
