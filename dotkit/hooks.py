"""Pre-commit hook: refuse files containing any of `blocked_words`.

Keep the list in config.local.yaml (never committed), for names such as an
employer or client that must not appear in this repo. Matching is whole-word and
case-insensitive; the hook reports file and line only, never the line's content.

Usage (from .pre-commit-config.yaml): python3 -m dotkit.hooks FILE...
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .config import ConfigError, load

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


def main(argv: list[str]) -> int:
    try:
        config = load(REPO / "config.yaml", REPO / "config.local.yaml")
    except ConfigError as exc:
        print(f"blocked-words: {exc}", file=sys.stderr)
        return 1
    hits = find_blocked(argv, config.blocked_words)
    for hit in hits:
        print(hit)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
