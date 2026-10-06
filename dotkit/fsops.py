"""Filesystem primitives shared by tasks: backups, links, managed blocks."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

BLOCK_START = "# >>> dotfiles >>>"
BLOCK_END = "# <<< dotfiles <<<"
_BLOCK = re.compile(rf"^{re.escape(BLOCK_START)}\n.*?^{re.escape(BLOCK_END)}\n?", re.M | re.S)


def backup(path: Path, home: Path, backup_dir: Path) -> Path:
    """Move ``path`` (file, dir or symlink) into ``backup_dir``, mirroring its place in home."""
    rel = path.relative_to(home) if path.is_relative_to(home) else path.relative_to(path.anchor)
    dest = backup_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(path, dest)
    return dest


def ensure_real_dir(directory: Path, home: Path, backup_dir: Path) -> None:
    """Make every component of ``directory`` below ``home`` a real directory.

    A symlinked or non-directory component is backed up first; otherwise new files
    would land wherever that symlink points (for example inside this repo).
    """
    current = home
    for part in directory.relative_to(home).parts:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            backup(current, home, backup_dir)
        current.mkdir(exist_ok=True)


def link_target(path: Path) -> Path | None:
    """Absolute, normalised destination of symlink ``path``, or None if it isn't one."""
    if not path.is_symlink():
        return None
    return Path(os.path.normpath(path.parent / path.readlink()))


def write_if_changed(path: Path, content: str) -> bool:
    """Write ``content`` unless the file already holds exactly that. Returns True on write."""
    if path.is_file() and not path.is_symlink() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(content)
    tmp.replace(path)
    return True


def upsert_block(text: str, body: str) -> str:
    """Insert or replace the dotfiles-managed block in ``text``; everything else is kept."""
    block = f"{BLOCK_START}\n{body.rstrip()}\n{BLOCK_END}\n"
    if _BLOCK.search(text):
        return _BLOCK.sub(lambda _: block, text, count=1)
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}\n{block}" if text else block


def display(path: Path, home: Path) -> str:
    """``~/``-relative path for messages."""
    return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)
