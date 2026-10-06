"""Nerd Fonts in ~/.local/share/fonts, so the prompt's icons render."""

from __future__ import annotations

import tarfile
import tempfile
from functools import partial
from pathlib import Path

from ..system import fetch, run
from .base import Change, Context, Task

# Python >= 3.11.4 supports extraction filters; use the strict one when available.
_SAFE = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
URL = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/{name}.tar.xz"


class Fonts(Task):
    name = "fonts"
    summary = "Download each Nerd Font in `fonts` to ~/.local/share/fonts (not on WSL)"

    def enabled(self, ctx: Context) -> bool:
        # WSL terminals render with Windows fonts; install those on the Windows side.
        return bool(ctx.config.fonts) and not ctx.facts.wsl

    def packages(self, ctx: Context) -> list[str]:
        return ["fontconfig"]

    def plan(self, ctx: Context) -> list[Change]:
        changes = []
        for name in ctx.config.fonts:
            target = _font_dir(ctx, name)
            if not (target.is_dir() and any(target.iterdir())):
                changes.append(Change(f"install {name} Nerd Font", partial(_install, ctx, name)))
        return changes


def _font_dir(ctx: Context, name: str) -> Path:
    return ctx.home / ".local" / "share" / "fonts" / "NerdFonts" / name


def _install(ctx: Context, name: str) -> None:
    target = _font_dir(ctx, name)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile() as tmp:
        tmp.write(fetch(URL.format(name=name), timeout=300))
        tmp.seek(0)
        with tarfile.open(fileobj=tmp, mode="r:xz") as archive:
            fonts = [m for m in archive.getmembers() if m.isfile() and m.name.endswith((".ttf", ".otf"))]
            for member in fonts:
                member.name = Path(member.name).name  # flatten; also defeats path traversal
                archive.extract(member, target, **_SAFE)
    run(["fc-cache", "-f", str(target)])
    ctx.note(f'Set your terminal font to "{name} Nerd Font" to see prompt icons.')
