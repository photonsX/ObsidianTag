import os
import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from models import Note, Tag, SharedTag, TagStats

CACHE_DIR = Path.home() / ".obsidian-tag-viewer"
CACHE_DB_FILE = CACHE_DIR / "cache.db"

class CacheManager:
    def __init__(self, db_path=CACHE_DB_FILE):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Files table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    modified_at REAL NOT NULL,
                    created_at REAL DEFAULT 0.0,
                    content_hash TEXT NOT NULL,
                    bucket TEXT DEFAULT 'note',
                    status TEXT DEFAULT 'hot',
                    attention TEXT DEFAULT 'settled',
                    daily_note INTEGER DEFAULT 0,
                    author TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    extra_metadata TEXT DEFAULT '{}',
                    is_ambiguous INTEGER DEFAULT 0,
                    detected_body_url TEXT DEFAULT ''
                )
            """)

            # Migration check: Ensure created_at & YAML columns exist in existing DB
            cursor.execute("PRAGMA table_info(files)")
            cols = [row["name"] for row in cursor.fetchall()]
            new_cols = {
                "created_at": "REAL DEFAULT 0.0",
                "bucket": "TEXT DEFAULT 'note'",
                "status": "TEXT DEFAULT 'hot'",
                "attention": "TEXT DEFAULT 'settled'",
                "daily_note": "INTEGER DEFAULT 0",
                "author": "TEXT DEFAULT ''",
                "url": "TEXT DEFAULT ''",
                "extra_metadata": "TEXT DEFAULT '{}'",
                "is_ambiguous": "INTEGER DEFAULT 0",
                "detected_body_url": "TEXT DEFAULT ''"
            }
            for cname, cdef in new_cols.items():
                if cname not in cols:
                    cursor.execute(f"ALTER TABLE files ADD COLUMN {cname} {cdef}")

            # Tags table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    count INTEGER DEFAULT 0
                )
            """)

            # Junction table: file_tags
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_tags (
                    file_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (file_id, tag_id),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                )
            """)

            # Materialized shared_tags co-occurrence table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shared_tags (
                    tag_a_id INTEGER NOT NULL,
                    tag_b_id INTEGER NOT NULL,
                    co_occurrence_count INTEGER DEFAULT 0,
                    PRIMARY KEY (tag_a_id, tag_b_id)
                )
            """)

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_modified ON files(modified_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_created ON files(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_bucket ON files(bucket)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_attention ON files(attention)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_ambiguous ON files(is_ambiguous)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_file ON file_tags(file_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_tags_tag ON file_tags(tag_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_shared_tags ON shared_tags(tag_a_id, tag_b_id)")
            
            conn.commit()

    def full_scan_update(self, notes_list: List[Note]) -> bool:
        import json
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")

                cursor.execute("DELETE FROM file_tags")
                cursor.execute("DELETE FROM files")
                cursor.execute("DELETE FROM tags")
                cursor.execute("DELETE FROM shared_tags")

                tag_id_map = {}
                tag_counts = {}
                file_tag_tuples = []

                for note in notes_list:
                    extra_json = json.dumps(note.extra_metadata) if note.extra_metadata else "{}"
                    cursor.execute(
                        """INSERT INTO files 
                        (path, title, modified_at, created_at, content_hash, bucket, status, attention, daily_note, author, url, extra_metadata, is_ambiguous, detected_body_url) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            note.path, note.title, note.modified_at, note.created_at, note.content_hash,
                            note.bucket, note.status, note.attention, 1 if note.daily_note else 0,
                            note.author, note.url, extra_json, 1 if note.is_ambiguous else 0, note.detected_body_url
                        )
                    )
                    file_id = cursor.lastrowid

                    for tag_name in note.tags:
                        clean_name = tag_name.lstrip("#").lower()
                        if clean_name not in tag_id_map:
                            cursor.execute("INSERT INTO tags (name, count) VALUES (?, 0)", (clean_name,))
                            tag_id = cursor.lastrowid
                            tag_id_map[clean_name] = tag_id
                            tag_counts[clean_name] = 0
                        else:
                            tag_id = tag_id_map[clean_name]

                        tag_counts[clean_name] += 1
                        file_tag_tuples.append((file_id, tag_id))

                for tag_name, count in tag_counts.items():
                    cursor.execute("UPDATE tags SET count = ? WHERE id = ?", (count, tag_id_map[tag_name]))

                cursor.executemany("INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)", file_tag_tuples)

                self._update_materialized_shared_tags(cursor)

                conn.commit()
                return True
        except Exception as e:
            print(f"Database error during full scan update: {e}")
            return False

    def _update_materialized_shared_tags(self, cursor):
        cursor.execute("DELETE FROM shared_tags")
        cursor.execute("""
            INSERT INTO shared_tags (tag_a_id, tag_b_id, co_occurrence_count)
            SELECT ft1.tag_id AS tag_a_id, ft2.tag_id AS tag_b_id, COUNT(*) AS co_occurrence_count
            FROM file_tags ft1
            JOIN file_tags ft2 ON ft1.file_id = ft2.file_id AND ft1.tag_id != ft2.tag_id
            GROUP BY ft1.tag_id, ft2.tag_id
        """)

    def incremental_update_file(self, note: Optional[Note], is_delete=False) -> bool:
        import json
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")

                cursor.execute("SELECT id FROM files WHERE path = ?", (note.path if note else "",))
                row = cursor.fetchone()
                file_id = row["id"] if row else None

                if file_id:
                    cursor.execute("DELETE FROM file_tags WHERE file_id = ?", (file_id,))
                    cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))

                if not is_delete and note:
                    extra_json = json.dumps(note.extra_metadata) if note.extra_metadata else "{}"
                    cursor.execute(
                        """INSERT INTO files 
                        (path, title, modified_at, created_at, content_hash, bucket, status, attention, daily_note, author, url, extra_metadata, is_ambiguous, detected_body_url) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            note.path, note.title, note.modified_at, note.created_at, note.content_hash,
                            note.bucket, note.status, note.attention, 1 if note.daily_note else 0,
                            note.author, note.url, extra_json, 1 if note.is_ambiguous else 0, note.detected_body_url
                        )
                    )
                    new_file_id = cursor.lastrowid

                    tag_tuples = []
                    for t_name in note.tags:
                        clean_name = t_name.lstrip("#").lower()
                        cursor.execute("INSERT OR IGNORE INTO tags (name, count) VALUES (?, 0)", (clean_name,))
                        cursor.execute("SELECT id FROM tags WHERE name = ?", (clean_name,))
                        t_id = cursor.fetchone()["id"]
                        tag_tuples.append((new_file_id, t_id))

                    cursor.executemany("INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)", tag_tuples)

                cursor.execute("""
                    UPDATE tags SET count = (
                        SELECT COUNT(*) FROM file_tags WHERE file_tags.tag_id = tags.id
                    )
                """)
                cursor.execute("DELETE FROM tags WHERE count = 0")

                self._update_materialized_shared_tags(cursor)

                conn.commit()
                return True
        except Exception as e:
            print(f"Error in incremental update: {e}")
            return False

    def get_all_tags(self, sort_by="count_desc", filter_query="", show_empty=False, show_orphans=True) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            order_clause = "t.count DESC, t.name ASC"
            if sort_by == "alphabetical":
                order_clause = "t.name ASC"
            elif sort_by == "modified_desc":
                order_clause = "MAX(f.modified_at) DESC"

            query = """
                SELECT t.id, t.name, t.count, MAX(f.modified_at) as max_mod
                FROM tags t
                LEFT JOIN file_tags ft ON t.id = ft.tag_id
                LEFT JOIN files f ON ft.file_id = f.id
                GROUP BY t.id, t.name, t.count
            """
            
            conditions = []
            params = []

            if not show_empty:
                conditions.append("t.count > 0")
            if not show_orphans:
                conditions.append("t.count > 0")
            if filter_query:
                conditions.append("(t.name LIKE ? OR f.title LIKE ?)")
                params.extend([f"%{filter_query}%", f"%{filter_query}%"])

            if conditions:
                query += " HAVING " + " AND ".join(conditions)

            query += f" ORDER BY {order_clause}"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "name": r["name"],
                    "count": r["count"],
                    "modified_at": r["max_mod"] or 0.0
                })

            # Calculate Untagged (Missing Tag) notes
            cursor.execute("""
                SELECT COUNT(f.id) as cnt, MAX(f.modified_at) as max_mod
                FROM files f
                LEFT JOIN file_tags ft ON f.id = ft.file_id
                WHERE ft.file_id IS NULL
            """)
            untagged_row = cursor.fetchone()
            untagged_cnt = untagged_row["cnt"] if untagged_row else 0
            untagged_mod = untagged_row["max_mod"] if untagged_row else 0.0

            if untagged_cnt > 0 and (not filter_query or "untagged" in filter_query.lower()):
                results.insert(0, {
                    "id": -1,
                    "name": "untagged",
                    "count": untagged_cnt,
                    "modified_at": untagged_mod or 0.0
                })

            return results

    def get_notes_for_tag(self, tag_name: str, filter_query="") -> List[dict]:
        clean_name = tag_name.lstrip("#").lower()
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if clean_name == "untagged":
                query = """
                    SELECT f.id, f.path, f.title, f.modified_at, f.content_hash
                    FROM files f
                    LEFT JOIN file_tags ft ON f.id = ft.file_id
                    WHERE ft.file_id IS NULL
                """
                params = []
                if filter_query:
                    query += " AND (f.title LIKE ? OR f.path LIKE ?)"
                    params.extend([f"%{filter_query}%", f"%{filter_query}%"])
                query += " ORDER BY f.title ASC"

                cursor.execute(query, params)
                note_rows = cursor.fetchall()

                return [{
                    "id": nr["id"],
                    "path": nr["path"],
                    "title": nr["title"],
                    "modified_at": nr["modified_at"],
                    "shared_tags_str": "[No Tags]",
                    "all_tags": []
                } for nr in note_rows]

            else:
                query = """
                    SELECT f.id, f.path, f.title, f.modified_at, f.content_hash
                    FROM files f
                    JOIN file_tags ft ON f.id = ft.file_id
                    JOIN tags t ON ft.tag_id = t.id
                    WHERE t.name = ?
                """
                params = [clean_name]

                if filter_query:
                    query += " AND (f.title LIKE ? OR f.path LIKE ?)"
                    params.extend([f"%{filter_query}%", f"%{filter_query}%"])

                query += " ORDER BY f.title ASC"

                cursor.execute(query, params)
                note_rows = cursor.fetchall()

                notes = []
                for nr in note_rows:
                    file_id = nr["id"]
                    cursor.execute("""
                        SELECT t.name
                        FROM tags t
                        JOIN file_tags ft ON t.id = ft.tag_id
                        WHERE ft.file_id = ? AND t.name != ?
                        ORDER BY t.name ASC
                    """, (file_id, clean_name))

                    other_tags = [f"#{row['name']}" for row in cursor.fetchall()]
                    shared_str = ", ".join(other_tags) if other_tags else "[Single Tag]"

                    notes.append({
                        "id": file_id,
                        "path": nr["path"],
                        "title": nr["title"],
                        "modified_at": nr["modified_at"],
                        "shared_tags_str": shared_str,
                        "all_tags": other_tags
                    })

                return notes

    def get_tag_stats(self) -> TagStats:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as cnt FROM tags WHERE count > 0")
            total_tags = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM files")
            total_notes = cursor.fetchone()["cnt"]

            cursor.execute("SELECT name, count FROM tags ORDER BY count DESC LIMIT 1")
            most_row = cursor.fetchone()
            most_name = most_row["name"] if most_row else "None"
            most_cnt = most_row["count"] if most_row else 0

            cursor.execute("SELECT COUNT(*) as cnt FROM tags WHERE count = 1")
            orphan_cnt = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM file_tags")
            total_assoc = cursor.fetchone()["cnt"]

            avg_tags = round(total_assoc / total_notes, 2) if total_notes > 0 else 0.0

            return TagStats(
                total_tags=total_tags,
                total_notes=total_notes,
                most_used_tag=f"#{most_name}" if most_name != "None" else "None",
                most_used_count=most_cnt,
                orphan_tags_count=orphan_cnt,
                avg_tags_per_note=avg_tags
            )

    def get_timeline_notes(self, start_ts: float = None, end_ts: float = None, sort_by: str = "modified_desc", filter_query: str = "") -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            date_col = "f.modified_at" if "modified" in sort_by else "f.created_at"
            order_dir = "DESC" if "desc" in sort_by else "ASC"

            query = f"""
                SELECT f.id, f.path, f.title, f.modified_at, f.created_at, f.content_hash
                FROM files f
                WHERE 1=1
            """
            params = []
            if start_ts is not None:
                query += f" AND {date_col} >= ?"
                params.append(start_ts)
            if end_ts is not None:
                query += f" AND {date_col} <= ?"
                params.append(end_ts)
            if filter_query:
                query += " AND (f.title LIKE ? OR f.path LIKE ?)"
                params.extend([f"%{filter_query}%", f"%{filter_query}%"])

            query += f" ORDER BY {date_col} {order_dir}"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            notes = []
            for r in rows:
                file_id = r["id"]
                cursor.execute("""
                    SELECT t.name
                    FROM tags t
                    JOIN file_tags ft ON t.id = ft.tag_id
                    WHERE ft.file_id = ?
                    ORDER BY t.name ASC
                """, (file_id,))
                tags_list = [f"#{row['name']}" for row in cursor.fetchall()]

                notes.append({
                    "id": file_id,
                    "path": r["path"],
                    "title": r["title"],
                    "modified_at": r["modified_at"],
                    "created_at": r["created_at"] if r["created_at"] > 0 else r["modified_at"],
                    "tags": tags_list
                })
            return notes

    def get_tag_timeline_stats(self, start_ts: float = None, end_ts: float = None, filter_query: str = "") -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT t.id, t.name, t.count as total_count,
                       MIN(f.created_at) as first_seen,
                       MAX(f.modified_at) as last_active,
                       COUNT(f.id) as range_count
                FROM tags t
                JOIN file_tags ft ON t.id = ft.tag_id
                JOIN files f ON ft.file_id = f.id
                WHERE 1=1
            """
            params = []
            if start_ts is not None:
                query += " AND f.modified_at >= ?"
                params.append(start_ts)
            if end_ts is not None:
                query += " AND f.modified_at <= ?"
                params.append(end_ts)
            if filter_query:
                query += " AND (t.name LIKE ? OR f.title LIKE ?)"
                params.extend([f"%{filter_query}%", f"%{filter_query}%"])

            query += " GROUP BY t.id, t.name ORDER BY last_active DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = []
            for r in rows:
                results.append({
                    "id": r["id"],
                    "name": r["name"],
                    "total_count": r["total_count"],
                    "range_count": r["range_count"],
                    "first_seen": r["first_seen"] or 0.0,
                    "last_active": r["last_active"] or 0.0
                })
            return results

    def get_daily_activity_counts(self, start_ts: float = None, end_ts: float = None) -> Dict[str, int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT modified_at FROM files WHERE 1=1"
            params = []
            if start_ts is not None:
                query += " AND modified_at >= ?"
                params.append(start_ts)
            if end_ts is not None:
                query += " AND modified_at <= ?"
                params.append(end_ts)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            counts = {}
            from datetime import datetime
            for r in rows:
                ts = r["modified_at"]
                if ts > 0:
                    day_key = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    counts[day_key] = counts.get(day_key, 0) + 1
            return counts

    def get_all_yaml_notes(self, bucket_filter: str = "All", status_filter: str = "All", attention_filter: str = "All", filter_query: str = "", only_ambiguous: bool = False, only_url_detected: bool = False) -> List[dict]:
        import json
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, path, title, modified_at, created_at, bucket, status, attention, daily_note, author, url, extra_metadata, is_ambiguous, detected_body_url
                FROM files
                WHERE 1=1
            """
            params = []
            if bucket_filter and bucket_filter != "All":
                query += " AND bucket = ?"
                params.append(bucket_filter)
            if status_filter and status_filter != "All":
                query += " AND status = ?"
                params.append(status_filter)
            if attention_filter and attention_filter != "All":
                query += " AND attention = ?"
                params.append(attention_filter)
            if only_ambiguous:
                query += " AND is_ambiguous = 1"
            if only_url_detected:
                query += " AND detected_body_url != ''"
            if filter_query:
                query += " AND (title LIKE ? OR path LIKE ? OR author LIKE ? OR url LIKE ?)"
                params.extend([f"%{filter_query}%", f"%{filter_query}%", f"%{filter_query}%", f"%{filter_query}%"])

            query += " ORDER BY modified_at DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()

            notes = []
            for r in rows:
                file_id = r["id"]
                cursor.execute("""
                    SELECT t.name
                    FROM tags t
                    JOIN file_tags ft ON t.id = ft.tag_id
                    WHERE ft.file_id = ?
                    ORDER BY t.name ASC
                """, (file_id,))
                tags_list = [f"#{row['name']}" for row in cursor.fetchall()]

                extra_dict = {}
                if r["extra_metadata"]:
                    try:
                        extra_dict = json.loads(r["extra_metadata"])
                    except Exception:
                        pass

                notes.append({
                    "id": file_id,
                    "path": r["path"],
                    "title": r["title"],
                    "modified_at": r["modified_at"],
                    "created_at": r["created_at"],
                    "bucket": r["bucket"] or "note",
                    "status": r["status"] or "hot",
                    "attention": r["attention"] or "settled",
                    "daily_note": bool(r["daily_note"]),
                    "author": r["author"] or "",
                    "url": r["url"] or "",
                    "extra_metadata": extra_dict,
                    "is_ambiguous": bool(r["is_ambiguous"]),
                    "detected_body_url": r["detected_body_url"] or "",
                    "tags": tags_list
                })
            return notes

    def get_ambiguous_notes_count(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM files WHERE is_ambiguous = 1")
            row = cursor.fetchone()
            return row["cnt"] if row else 0


