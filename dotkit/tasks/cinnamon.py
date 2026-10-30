"""Linux Mint Cinnamon look and feel: Spices applets and themes, applet settings, and the
dconf settings saved in desktop/cinnamon/ by scripts/mint/cinnamon-capture.sh.

Only runs on a desktop profile, on Linux Mint, with Cinnamon installed: these settings
mean nothing (or worse) to other desktops. It is a one-time task, so changes made later
in System Settings are not reverted on the next run; editing desktop/cinnamon/ or the
`cinnamon` config makes it apply again.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import tempfile
import zipfile
from functools import partial
from pathlib import Path
from urllib.parse import quote

from ..fsops import backup
from ..system import fetch, output, run
from .base import Change, Context, Task

SPICES = "https://cinnamon-spices.linuxmint.com/files/{kind}/{name}.zip"


class Cinnamon(Task):
    name = "cinnamon"
    summary = "Linux Mint + Cinnamon desktops: Spices applets/themes and saved desktop settings"
    once = True

    def enabled(self, ctx: Context) -> bool:
        return (
            ctx.config.cinnamon.enabled
            and ctx.facts.distro_id == "linuxmint"
            and not ctx.facts.wsl
            and shutil.which("cinnamon") is not None
        )

    def packages(self, ctx: Context) -> list[str]:
        return ["dconf-cli", *ctx.config.cinnamon.packages]

    def fingerprint(self, ctx: Context) -> object:
        files = sorted(p for p in _settings_dir(ctx).rglob("*") if p.is_file())
        digest = hashlib.sha256()
        for path in files:
            digest.update(str(path.relative_to(ctx.repo)).encode() + b"\0" + path.read_bytes())
        return {"config": ctx.config.cinnamon, "files": digest.hexdigest()}

    def plan(self, ctx: Context) -> list[Change]:
        cfg, changes = ctx.config.cinnamon, []
        applets = ctx.home / ".local/share/cinnamon/applets"
        for uuid in cfg.applets:
            if not (applets / uuid).is_dir():
                changes.append(Change(f"install applet {uuid}", partial(_spice, "applets", uuid, applets)))
        themes = ctx.home / ".themes"
        for theme in cfg.themes:
            if not any((d / theme).is_dir() for d in (themes, ctx.home / ".local/share/themes")):
                changes.append(Change(f"install theme {theme}", partial(_spice, "themes", theme, themes)))

        spices = _stale_spice_settings(ctx)
        if spices:
            summary = f"apply {len(spices)} applet settings file(s) to ~/.config/cinnamon/spices"
            changes.append(Change(summary, partial(_copy_spice_settings, ctx, spices)))

        ini = _settings_dir(ctx) / "dconf.ini"
        if ini.is_file():
            differ = _dconf_diff(ini.read_text(), output(["dconf", "dump", "/"]))
            if differ:
                changes.append(Change(f"apply {len(differ)} desktop setting(s) (dconf)", partial(_load, ini)))
        if changes:
            ctx.note("Restart Cinnamon (Ctrl+Alt+Esc) or log out and back in to see the new look.")
        return changes


def _settings_dir(ctx: Context) -> Path:
    return ctx.repo / "desktop" / "cinnamon"


def _spice(kind: str, name: str, dest: Path) -> None:
    """Download a Spice zip (one top-level folder named after it) into ``dest``."""
    data = fetch(SPICES.format(kind=kind, name=quote(name, safe="@+")), timeout=300)
    with zipfile.ZipFile(io.BytesIO(data)) as archive, tempfile.TemporaryDirectory() as tmp:
        for member in archive.namelist():
            parts = Path(member).parts
            if not parts or parts[0] != name or ".." in parts or Path(member).is_absolute():
                raise OSError(f"{name}.zip: unexpected entry {member!r}")
        archive.extractall(tmp)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(Path(tmp) / name), dest / name)


def _stale_spice_settings(ctx: Context) -> list[Path]:
    """Saved applet settings (relative paths) that differ from the live ones."""
    src = _settings_dir(ctx) / "spices"
    if not src.is_dir():
        return []
    live = ctx.home / ".config/cinnamon/spices"
    stale = []
    for path in sorted(src.rglob("*.json")):
        rel = path.relative_to(src)
        target = live / rel
        # Cinnamon writes no final newline; the repo's pre-commit hooks add one.
        if not target.is_file() or target.read_bytes().rstrip() != path.read_bytes().rstrip():
            stale.append(rel)
    return stale


def _copy_spice_settings(ctx: Context, files: list[Path]) -> None:
    src, live = _settings_dir(ctx) / "spices", ctx.home / ".config/cinnamon/spices"
    for rel in files:
        target = live / rel
        if target.exists() or target.is_symlink():
            backup(target, ctx.home, ctx.backup_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, target)


def _load(ini: Path) -> None:
    run(["dconf", "load", "/"], input=ini.read_text())


def _dconf_diff(wanted: str, current: str) -> list[str]:
    """Keys (as /path/key) whose value in ``wanted`` differs from the ``current`` dump."""
    have = _parse_dump(current)
    return [key for key, value in _parse_dump(wanted).items() if have.get(key) != value]


def _parse_dump(text: str) -> dict[str, str]:
    """`dconf dump` keyfile text -> {"/section/key": "gvariant text"}."""
    values, section = {}, ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip("/")
            continue
        key, sep, value = line.partition("=")
        if sep:
            values[f"/{section}/{key.strip()}".replace("//", "/")] = value.strip()
    return values
