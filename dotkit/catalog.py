"""The choices the web configurator offers, read from config.yaml and windows/personas.json.

Output only: nothing here changes a machine. It is committed as web/public/catalog.json
and a test keeps the two in step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from .config import HardenLevel, load


def build(repo: Path) -> dict[str, object]:
    config = load(repo / "config.yaml", home_dir=repo / "home")
    windows = json.loads((repo / "windows" / "personas.json").read_text())
    return {
        "linux": {
            "harden": list(get_args(HardenLevel)),
            "personas": {
                name: {"about": p.about, "docker": p.docker, "apps": list(p.apps)}
                for name, p in config.personas.items()
            },
            "apps": {name: {"about": a.about, "when": list(a.when)} for name, a in config.apps.items()},
            "base": {"packages": list(config.packages), "tools": list(config.tools)},
        },
        "windows": {"personas": {name: {"about": p["about"]} for name, p in windows.items()}},
    }


def dump(repo: Path) -> str:
    return json.dumps(build(repo), indent=2, ensure_ascii=False) + "\n"
