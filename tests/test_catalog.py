"""The data behind the web configurator (spec 0004)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from dotkit.catalog import build
from dotkit.config import load

CATALOG = Path("web/public/catalog.json")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _config():
    return load(Path("config.yaml"), home_dir=Path("home"))


def test_every_app_has_a_description():
    missing = [n for n, a in _config().apps.items() if not a.about.strip()]
    assert not missing, f"add `about:` to {missing} in config.yaml"


def test_catalog_lists_personas_apps_and_windows_personas():
    data = build(Path())
    config = _config()
    assert set(data["linux"]["personas"]) == set(config.personas)
    assert set(data["linux"]["apps"]) == set(config.apps)
    assert data["linux"]["apps"]["jan"]["when"] == ["desktop", "heavy"]
    assert data["linux"]["harden"] == ["none", "standard", "aggressive"]
    assert set(data["windows"]["personas"]) >= set(config.personas)
    for name in [*data["linux"]["personas"], *data["linux"]["apps"], *data["windows"]["personas"]]:
        assert NAME.match(name), name


def test_committed_catalog_is_current():
    assert json.loads(CATALOG.read_text()) == build(Path()), (
        "run: ./install.sh catalog > web/public/catalog.json"
    )


def test_catalog_command_prints_the_same_json():
    out = subprocess.run(
        ["python3", "-m", "dotkit", "catalog"], capture_output=True, text=True, check=True
    ).stdout
    assert json.loads(out) == build(Path())


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_logic():
    subprocess.run(["node", "--test", "web/public/logic.test.mjs", "web/worker.test.mjs"], check=True)
