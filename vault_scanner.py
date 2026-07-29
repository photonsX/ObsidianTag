import os
import re
import hashlib
import frontmatter
from pathlib import Path
from typing import List, Set, Optional, Tuple
from PyQt6.QtCore import QThread, pyqtSignal
from models import Note

IGNORED_DIRS = {".obsidian", ".git", ".trash", "templates", "node_modules"}

class VaultScanner:
    @staticmethod
    def scan_file(abs_path: Path, vault_root: Path) -> Optional[Note]:
        """
        Parses a single Markdown file for YAML frontmatter tags and inline body #tags.
        Handles code block stripping and nested tags like #project/active.
        """
        try:
            rel_path = str(abs_path.relative_to(vault_root)).replace("\\", "/")
            mtime = abs_path.stat().st_mtime

            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            title = abs_path.stem

            # Parse frontmatter and body using python-frontmatter
            fm_tags = set()
            try:
                post = frontmatter.loads(content)
                tags_val = post.metadata.get("tags") or post.metadata.get("tag")
                if isinstance(tags_val, str):
                    fm_tags.update(t.strip() for t in re.split(r"[,,\s]+", tags_val) if t.strip())
                elif isinstance(tags_val, list):
                    for t in tags_val:
                        if isinstance(t, str):
                            fm_tags.update(x.strip() for x in re.split(r"[,,\s]+", t) if x.strip())
                body_content = post.content
            except Exception:
                body_content = content

            # Extract inline tags from body, ignoring code blocks
            inline_tags = VaultScanner._extract_inline_tags(body_content)

            # Combine tags and normalize
            all_tags = set()
            for t in fm_tags:
                all_tags.add(t.lstrip("#").lower())
            for t in inline_tags:
                all_tags.add(t.lstrip("#").lower())

            return Note(
                path=rel_path,
                title=title,
                modified_at=mtime,
                content_hash=content_hash,
                tags=all_tags
            )

        except Exception as e:
            print(f"Error scanning file {abs_path}: {e}")
            return None

    @staticmethod
    def _extract_inline_tags(body: str) -> Set[str]:
        """
        Extracts #tags from body text while skipping code blocks ```...``` and inline code `...`.
        Supports nested tags like #project/active.
        """
        # 1. Strip fenced code blocks
        cleaned = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
        # 2. Strip inline code spans
        cleaned = re.sub(r"`.*?`", "", cleaned)

        tags = set()
        for line in cleaned.splitlines():
            line_stripped = line.strip()
            # Ignore markdown headers like # Header
            if line_stripped.startswith("#") and (len(line_stripped) == 1 or line_stripped[1] == " "):
                continue

            # Match #tag or #nested/tag/name (letters, numbers, _, -, /)
            matches = re.findall(r"(?:^|\s)#([a-zA-Z0-9_\-/]+)", line)
            for m in matches:
                # Exclude pure numbers or hex colors like #fff or #123456
                if not m.isdigit() and not re.match(r"^[0-9a-fA-F]{3,6}$", m):
                    tags.add(m.lower())

        return tags


class VaultScanWorker(QThread):
    progress = pyqtSignal(int, int, str)  # current, total, filename
    finished = pyqtSignal(list)           # List[Note]
    error = pyqtSignal(str)

    def __init__(self, vault_path: str):
        super().__init__()
        self.vault_path = Path(vault_path)

    def run(self):
        if not self.vault_path.exists() or not self.vault_path.is_dir():
            self.error.emit(f"Vault path does not exist: {self.vault_path}")
            return

        md_files = []
        for root, dirs, files in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            for file in files:
                if file.endswith(".md"):
                    md_files.append(Path(root) / file)

        total_files = len(md_files)
        notes = []

        for idx, abs_path in enumerate(md_files, 1):
            note = VaultScanner.scan_file(abs_path, self.vault_path)
            if note:
                notes.append(note)
            self.progress.emit(idx, total_files, abs_path.name)

        self.finished.emit(notes)
