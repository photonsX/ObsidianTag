from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional
from datetime import datetime

@dataclass
class Note:
    id: Optional[int] = None
    path: str = ""
    title: str = ""
    modified_at: float = 0.0
    created_at: float = 0.0
    content_hash: str = ""
    tags: Set[str] = field(default_factory=set)

    @property
    def modified_date_str(self) -> str:
        if self.modified_at > 0:
            return datetime.fromtimestamp(self.modified_at).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    @property
    def created_date_str(self) -> str:
        if self.created_at > 0:
            return datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

@dataclass
class Tag:
    id: Optional[int] = None
    name: str = ""
    count: int = 0
    color: str = "#007acc"

@dataclass
class SharedTag:
    tag_a_id: int
    tag_b_id: int
    co_occurrence_count: int

@dataclass
class VaultInfo:
    vault_path: str = ""
    total_files: int = 0
    total_tags: int = 0
    last_scanned: float = 0.0

@dataclass
class TagStats:
    total_tags: int = 0
    total_notes: int = 0
    most_used_tag: str = "None"
    most_used_count: int = 0
    orphan_tags_count: int = 0
    avg_tags_per_note: float = 0.0
