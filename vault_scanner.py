import os
import re
import hashlib
import frontmatter
from datetime import datetime
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
            stat_res = abs_path.stat()
            mtime = stat_res.st_mtime
            ctime = getattr(stat_res, "st_birthtime", stat_res.st_ctime)

            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            title = abs_path.stem

            # Parse frontmatter and body using python-frontmatter
            fm_tags = set()
            bucket = "note"
            status = "hot"
            attention = "settled"
            daily_note = False
            author = ""
            url = ""
            extra_metadata = {}
            is_ambiguous = False
            body_content = content

            try:
                post = frontmatter.loads(content)
                body_content = post.content
                meta = dict(post.metadata)

                # 1. Tags
                tags_val = meta.pop("tags", None) or meta.pop("tag", None)
                if isinstance(tags_val, str):
                    fm_tags.update(t.strip() for t in re.split(r"[,,\s]+", tags_val) if t.strip())
                elif isinstance(tags_val, list):
                    for t in tags_val:
                        if isinstance(t, str):
                            fm_tags.update(x.strip() for x in re.split(r"[,,\s]+", t) if x.strip())

                # 2. Bucket
                bucket_val = str(meta.pop("bucket", "") or meta.pop("type", "")).strip().lower()
                if bucket_val in {"note", "idea", "wip", "task", "dailynote"}:
                    bucket = bucket_val
                elif bucket_val in {"daily", "daily-note", "journal"}:
                    bucket = "dailynote"
                elif bucket_val:
                    is_ambiguous = True

                # 3. Status (Heat)
                status_val = str(meta.pop("status", "")).strip().lower()
                if status_val in {"hot", "warm", "cool", "cold"}:
                    status = status_val
                elif status_val in {"seed", "draft", "raw", "new", "editing", "in-progress"}:
                    status = "hot"
                elif status_val in {"developing", "polished", "curated", "evergreen"}:
                    status = "warm"
                elif status_val in {"final", "done", "locked"}:
                    status = "cool"
                elif status_val in {"archived", "stored"}:
                    status = "cold"
                elif status_val:
                    is_ambiguous = True

                # 4. Attention
                att_val = str(meta.pop("attention", "") or meta.pop("action", "")).strip().lower()
                if att_val in {"settled", "needs-revisit", "pinned"}:
                    attention = att_val
                elif att_val in {"open", "revisit", "todo", "needs-review"}:
                    attention = "needs-revisit"
                elif att_val:
                    is_ambiguous = True

                # 5. Daily Note
                dn_val = meta.pop("daily_note", None) or meta.pop("is_daily", None) or meta.pop("daily", None)
                if dn_val is not None:
                    daily_note = bool(dn_val)

                # 6. Author
                author_val = meta.pop("author", None)
                if author_val:
                    author = str(author_val).strip()

                # 7. URL
                url_val = meta.pop("url", None) or meta.pop("link", None)
                if url_val:
                    url = str(url_val).strip()

                # 8. Creation Timestamp (YAML header priority, fallback to OS ctime)
                created_val = meta.pop("created", None) or meta.pop("created_at", None) or meta.pop("date", None)
                if created_val:
                    try:
                        if isinstance(created_val, (int, float)):
                            ctime = float(created_val)
                        elif hasattr(created_val, "timestamp"):
                            ctime = created_val.timestamp()
                        else:
                            created_str = str(created_val).strip()
                            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d"):
                                try:
                                    dt = datetime.strptime(created_str[:19], fmt)
                                    ctime = dt.timestamp()
                                    break
                                except ValueError:
                                    pass
                    except Exception:
                        pass

                # 9. Extra Metadata (preserves all custom/unknown keys)
                extra_metadata = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in meta.items()}

            except Exception as e:
                is_ambiguous = True
                body_content = content

            # Body URL Scanner (if url property is missing)
            detected_url = ""
            url_match = re.search(r"https?://[^\s><\"\')]+", body_content)
            if url_match and not url:
                detected_url = url_match.group(0)

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
                created_at=ctime,
                content_hash=content_hash,
                tags=all_tags,
                bucket=bucket,
                status=status,
                attention=attention,
                daily_note=daily_note,
                author=author,
                url=url,
                extra_metadata=extra_metadata,
                is_ambiguous=is_ambiguous,
                detected_body_url=detected_url
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
