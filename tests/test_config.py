from __future__ import annotations

import re
from pathlib import Path

import pytest

from dotkit.config import ConfigError, load, merge


def _load(tmp_path: Path, text: str, local: str | None = None, modules=()):
    base = tmp_path / "config.yaml"
    base.write_text(text)
    overlay = tmp_path / "config.local.yaml"
    if local is not None:
        overlay.write_text(local)
    home = tmp_path / "home"
    for m in modules:
        (home / m).mkdir(parents=True, exist_ok=True)
    return load(base, overlay, home_dir=home if modules else None)


def test_defaults_from_empty_file(tmp_path):
    cfg = _load(tmp_path, "")
    assert cfg.shells.default == "bash"
    assert cfg.nvidia.enabled == "auto"


def test_full_example_parses(tmp_path):
    cfg = _load(
        tmp_path, Path("config.yaml").read_text(), modules=["git", "nvim", "tmux", "starship", "kind"]
    )
    assert cfg.shells.default == "fish"
    assert all(isinstance(v, str) for v in cfg.tools.values())
    assert cfg.enabled_modules[:4] == ("fish", "zsh", "bash", "shell")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("shells: {default: fsh, install: [fish]}", "shells.default: expected fish | zsh | bash"),
        ("shells: {default: zsh, install: [fish]}", "must also be in shells.install"),
        ("colour: red", "unknown key 'colour'"),
        ("tools: {python: 3.12}", "tools.python: expected a string (quote it"),
        ("docker: {enabled: yes please}", "docker.enabled: expected true or false"),
        ("nvidia: {enabled: maybe}", "nvidia.enabled: expected"),
        ("packages: git", "packages: expected a list"),
        ("aliases: {'bad name': x}", "invalid alias name"),
        ("modules: [fish]", "enabled automatically"),
        ("apt_repos: {x: {key: k, url: u}}", "apt_repos.x.packages: list at least one"),
        ("mask: [{replace: x}]", "mask[0]: missing required key(s): pattern"),
    ],
)
def test_validation_errors(tmp_path, text, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        _load(tmp_path, text)


def test_unknown_module_lists_available(tmp_path):
    with pytest.raises(ConfigError, match=r"no such module 'vim' \(available: git\)"):
        _load(tmp_path, "modules: [vim]", modules=["git"])


def test_local_overlay_merges_and_deletes(tmp_path):
    cfg = _load(
        tmp_path,
        "tools: {node: lts, kind: latest}\npackages: [a, b]",
        local="tools: {kind: null, uv: latest}\npackages: [c]",
    )
    assert cfg.tools == {"node": "lts", "uv": "latest"}
    assert cfg.packages == ("c",)


def test_merge_is_recursive():
    assert merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_error_names_the_files(tmp_path):
    with pytest.raises(ConfigError, match=r"^config.yaml \+ config.local.yaml: "):
        _load(tmp_path, "", local="bogus: 1")
