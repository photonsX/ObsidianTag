# Obsidian Tag Viewer & Editor 💎

A high-performance, native Python (**PyQt6**) desktop application for viewing, searching, inspecting, and inline editing tags and Markdown notes across your Obsidian vaults.

---

## 🌟 Core Features

- **⚡ Fast Vault Scanner**: Asynchronous non-blocking QThread scanner parsing YAML frontmatter tags (strings & lists) and inline `#tags` while skipping code blocks (` ``` ` and `` ` ``). Supports nested tags (e.g. `#project/active`).
- **💾 SQLite Local Cache**: Stores files, tags, and a materialized co-occurrence `shared_tags` matrix at `~/.obsidian-tag-viewer/cache.db` with indexes for handling 50,000+ notes smoothly.
- **📊 Expandable Tree Layout**: Top-level tag rows sorted by note count with deterministic color dot indicators; expanding a tag displays child notes with co-occurring shared tags (e.g., `#meeting, #todo/high`).
- **🔍 Debounced Search Bar**: Real-time filtering across tag names and note titles with debouncing (300ms) and Escape reset.
- **📝 Full-Width Inline Note Editor**: Monospace code editor (`Consolas` / `Fira Code`) with line numbers, 4-space tab indentation, `[SAVE]` / `[CANCEL]` toolbar, Ctrl+S and Escape keyboard shortcuts, and green row flash confirmation on save.
- **👀 Background File Watcher**: Automatic real-time filesystem monitoring via `watchdog` with 500ms debouncing for instant incremental cache updates without UI freezing.
- **📊 Statistics & CSV Export**: Detailed tag statistics popup and full view export to CSV.

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11 or higher.

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Application
```bash
python main.py
```

---

## 📦 Distribution Packaging (PyInstaller)

To build a single-file standalone executable for Windows / macOS / Linux:

```bash
pyinstaller --noconsole --onefile --name "ObsidianTagViewer" main.py
```

The compiled binary will be placed inside the `dist/` directory.

---

## 🖥️ UI Layout Overview

```text
┌──────────────────────────────────────────────────────────┐
│  [Search Bar: filter tags/notes as you type          ]   │
├─────────────────┬────────┬───────────────────────────────┤
│  TAG / NOTE     │ COUNT  │  SHARED TAGS                  │
├─────────────────┼────────┼───────────────────────────────┤
│ ▶ 🔵 #project   │   12   │                               │
│   📄 Alpha.md   │    -   │  #meeting, #todo/high         │
│   📄 Beta.md    │    -   │  #person/john                 │
│ ▶ 🟣 #meeting   │   45   │                               │
│   📄 Standup.md │    -   │  #daily, #team                │
└─────────────────┴────────┴───────────────────────────────┘
```
