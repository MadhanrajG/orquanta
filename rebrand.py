#!/usr/bin/env python3
"""
OrQuanta Rebrand Script
=======================
Renames all OrQuanta → OrQuanta references across c:\\ai-gpu-cloud\\v4\\
Creates a full backup at c:\\ai-gpu-cloud\\v4_backup\\ first.

Run: python rebrand.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

# ─── Config ───────────────────────────────────────────────────────────────────

SOURCE_DIR  = Path(r"c:\ai-gpu-cloud\v4")
BACKUP_DIR  = Path(r"c:\ai-gpu-cloud\v4_backup")
ROOT_DIR    = Path(r"c:\ai-gpu-cloud")   # also rebrand root-level .py/.md files

SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".mypy_cache", ".tox", "v4_backup"}

# Text replacements — ORDER MATTERS (most specific first)
TEXT_REPLACEMENTS = [
    # Version strings
    ("OrQuanta Agentic v1.0",  "OrQuanta Agentic v1.0"),
    ("OrQuanta Agentic v1",    "OrQuanta Agentic v1"),
    ("OrQuanta Agentic",       "OrQuanta Agentic"),
    # OrMind → OrMind
    ("OrMind",          "OrMind"),
    ("OrMind",           "OrMind"),
    ("or_mind",          "or_mind"),
    ("or-mind",          "or-mind"),
    # Docker images
    ("orquanta:latest",        "orquanta:latest"),
    ("orquanta/api",           "orquanta/api"),
    # Mixed case
    ("OrQuanta",               "OrQuanta"),
    ("ORQUANTA",               "ORQUANTA"),
    ("orquanta",              "orquanta"),
    ("orquanta",               "orquanta"),
    # Logger names
    ("orquanta.agents",        "orquanta.agents"),
    ("orquanta.billing",       "orquanta.billing"),
    ("orquanta.memory",        "orquanta.memory"),
    ("orquanta.healing",       "orquanta.healing"),
    ("orquanta.audit",         "orquanta.audit"),
    ("orquanta.memory",        "orquanta.memory"),
]

# File extensions to do text replacement on
TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".html", ".js", ".jsx",
    ".ts", ".tsx", ".css", ".scss", ".env", ".toml", ".cfg", ".ini",
    ".sh", ".bash", ".dockerfile", ".tf", ".tfvars",
}

# File name replacements (old_substring → new_substring)
FILE_NAME_REPLACEMENTS = [
    ("orquanta_kernel_bridge", "orquanta_kernel_bridge"),
    ("orquanta_kernel_final",  "orquanta_kernel_final"),
    ("orquanta",               "orquanta"),
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def replace_text(content: str) -> tuple[str, int]:
    """Apply all text replacements. Returns (new_content, replacement_count)."""
    total = 0
    for old, new in TEXT_REPLACEMENTS:
        count = content.count(old)
        if count:
            content = content.replace(old, new)
            total += count
    return content, total


def new_filename(name: str) -> str:
    """Return new filename after applying name replacements."""
    result = name
    for old, new in FILE_NAME_REPLACEMENTS:
        result = result.replace(old, new)
    return result


# ─── Step 1: Backup ───────────────────────────────────────────────────────────

def create_backup() -> None:
    print(f"\n{'='*60}")
    print("STEP 1: Creating backup...")
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Backup: {BACKUP_DIR}")

    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
        print(f"  [i] Removed existing backup.")

    shutil.copytree(SOURCE_DIR, BACKUP_DIR)
    print(f"  [OK] Backup created at {BACKUP_DIR}")

    # Also backup root-level files
    root_backup = Path(r"c:\ai-gpu-cloud\root_backup")
    root_backup.mkdir(exist_ok=True)
    for f in ROOT_DIR.glob("*.py"):
        shutil.copy2(f, root_backup / f.name)
    for f in ROOT_DIR.glob("*.md"):
        shutil.copy2(f, root_backup / f.name)
    for f in ROOT_DIR.glob("*.json"):
        shutil.copy2(f, root_backup / f.name)
    print(f"  [OK] Root files backed up to {root_backup}")


# ─── Step 2: Text Replacement ─────────────────────────────────────────────────

def run_text_replacements(scan_dirs: list[Path]) -> dict:
    print(f"\n{'='*60}")
    print("STEP 2: Running text replacements...")

    stats = {
        "files_scanned": 0,
        "files_modified": 0,
        "total_replacements": 0,
        "modified_files": [],
        "errors": [],
    }

    for scan_dir in scan_dirs:
        for fpath in scan_dir.rglob("*"):
            if fpath.is_dir():
                continue
            if should_skip(fpath):
                continue
            if fpath.suffix.lower() not in TEXT_EXTENSIONS:
                continue

            stats["files_scanned"] += 1

            try:
                # Try UTF-8 first, fallback to latin-1
                try:
                    content = fpath.read_text(encoding="utf-8")
                    encoding = "utf-8"
                except UnicodeDecodeError:
                    content = fpath.read_text(encoding="latin-1")
                    encoding = "latin-1"

                new_content, count = replace_text(content)

                if count > 0:
                    fpath.write_text(new_content, encoding=encoding)
                    stats["files_modified"] += 1
                    stats["total_replacements"] += count
                    stats["modified_files"].append({
                        "file": str(fpath.relative_to(ROOT_DIR)),
                        "replacements": count,
                    })
                    print(f"  [{count:3d} changes] {fpath.relative_to(ROOT_DIR)}")

            except Exception as exc:
                stats["errors"].append(f"{fpath}: {exc}")
                print(f"  [ERROR] {fpath}: {exc}")

    return stats


# ─── Step 3: File Renames ─────────────────────────────────────────────────────

def run_file_renames(scan_dirs: list[Path]) -> list[str]:
    print(f"\n{'='*60}")
    print("STEP 3: Renaming files...")
    renamed = []

    for scan_dir in scan_dirs:
        # Collect files first (rename after full scan to avoid iterator issues)
        files_to_rename = []
        for fpath in scan_dir.rglob("*"):
            if should_skip(fpath):
                continue
            old_name = fpath.name
            new_name = new_filename(old_name)
            if new_name != old_name:
                files_to_rename.append((fpath, fpath.parent / new_name))

        for old_path, new_path in files_to_rename:
            try:
                old_path.rename(new_path)
                rel_old = old_path.relative_to(ROOT_DIR)
                rel_new = new_path.relative_to(ROOT_DIR)
                print(f"  RENAMED: {rel_old} → {rel_new}")
                renamed.append(f"{rel_old} → {rel_new}")
            except Exception as exc:
                print(f"  [ERROR] rename {old_path}: {exc}")

    return renamed


# ─── Step 4: Print Report ─────────────────────────────────────────────────────

def print_report(stats: dict, renamed: list[str]) -> None:
    print(f"\n{'='*60}")
    print("REBRAND REPORT")
    print(f"{'='*60}")
    print(f"  Files scanned:      {stats['files_scanned']}")
    print(f"  Files modified:     {stats['files_modified']}")
    print(f"  Total replacements: {stats['total_replacements']}")
    print(f"  Files renamed:      {len(renamed)}")
    print(f"  Errors:             {len(stats['errors'])}")
    print()

    if renamed:
        print("  Files Renamed:")
        for r in renamed:
            print(f"    {r}")
        print()

    if stats["errors"]:
        print("  ERRORS:")
        for e in stats["errors"]:
            print(f"    {e}")
        print()

    print(f"{'='*60}")
    print(f"  Backup:  c:\\ai-gpu-cloud\\v4_backup\\")
    print(f"  Status:  REBRAND COMPLETE — OrQuanta is now OrQuanta")
    print(f"{'='*60}\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "="*60)
    print("  OrQuanta Rebrand Engine v1.0")
    print("  OrQuanta → OrQuanta | OrMind → OrMind")
    print("="*60)

    # Directories to scan (v4/ + root-level files)
    scan_dirs = [SOURCE_DIR, ROOT_DIR]

    create_backup()

    # Text replacements across v4/ and root .py/.md/.json
    stats = run_text_replacements(scan_dirs)

    # File renames (v4/ only, to avoid renaming root scripts)
    renamed = run_file_renames([SOURCE_DIR])

    print_report(stats, renamed)


if __name__ == "__main__":
    main()
