"""Pre-commit hook: refuse files containing any of `blocked_words`.

Keep the list in config.local.yaml (never committed), for names such as an
employer or client that must not appear in this repo. Matching is whole-word and
case-insensitive; the hook reports file and line only, never the line's content.

Usage (from .pre-commit-config.yaml): python -m dotkit.hooks FILE...

Only `blocked_words` is read, so a problem elsewhere in the config never blocks a
commit here (./install.sh reports those).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def find_blocked(files: list[str], words: tuple[str, ...]) -> list[str]:
    if not words:
        return []
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)
    hits = []
    for name in files:
        try:
            text = Path(name).read_text(errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if match := pattern.search(line):
                hits.append(f"{name}:{number}: contains blocked word {match.group(0)!r}")
    return hits


def blocked_words(*files: Path) -> tuple[str, ...]:
    """`blocked_words` from the last of ``files`` that sets it."""
    words: object = []
    for path in files:
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except FileNotFoundError:
            continue
        if isinstance(data, dict) and "blocked_words" in data:
            words = data["blocked_words"] or []
    if not isinstance(words, list):
        raise ValueError("blocked_words must be a list of words")
    return tuple(str(w) for w in words if str(w).strip())


def main(argv: list[str]) -> int:
    try:
        words = blocked_words(REPO / "config.yaml", REPO / "config.local.yaml")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"blocked-words: {exc}", file=sys.stderr)
        return 1
    hits = find_blocked(argv, words)
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
