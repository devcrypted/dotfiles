"""The Windows package data: the base list and the personas must stay consistent."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

WINDOWS = Path("windows")
# Personas that only make sense on Windows.
WINDOWS_ONLY = {"devops"}


def _base_ids() -> set[str]:
    data = json.loads((WINDOWS / "packages.json").read_text())
    return {p["PackageIdentifier"] for source in data["Sources"] for p in source["Packages"]}


def _personas() -> dict[str, dict]:
    return json.loads((WINDOWS / "personas.json").read_text())


def test_every_persona_says_what_it_is_and_lists_packages():
    for name, persona in _personas().items():
        assert persona["about"].strip(), name
        assert persona["packages"], name
        assert len(persona["packages"]) == len(set(persona["packages"])), f"{name} lists a package twice"


def test_a_package_is_either_in_the_base_or_in_a_persona():
    base = _base_ids()
    for name, persona in _personas().items():
        both = base & set(persona["packages"])
        assert not both, f"{name} repeats base packages: {sorted(both)}"


def test_personas_shared_with_linux_have_the_same_names():
    linux = set(yaml.safe_load(Path("config.yaml").read_text())["personas"])
    windows = set(_personas())
    assert linux - windows == set(), "a Linux persona is missing on Windows"
    assert windows - linux == WINDOWS_ONLY


def test_the_base_list_is_a_valid_winget_import_file():
    data = json.loads((WINDOWS / "packages.json").read_text())
    assert data["$schema"].startswith("https://aka.ms/winget-packages")
    assert [s["SourceDetails"]["Name"] for s in data["Sources"]] == ["winget", "msstore"]
