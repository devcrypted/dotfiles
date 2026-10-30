"""Apps from `apps` that apt and mise can't install: flatpaks, .deb downloads, scripts.

Their `apt`, `apt_repo` and `mise` sources were already folded into `packages`,
`apt_repos` and `tools` by `config.resolve`, so those tasks install them.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path

from ..config import Deb, Script
from ..system import CommandError, fetch, output, run
from .base import Change, Context, Task

FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"


class Apps(Task):
    name = "apps"
    summary = "Install `apps` that come as a flatpak, a .deb download or an install script"

    def enabled(self, ctx: Context) -> bool:
        return any(a.flatpak or a.deb or a.script for a in ctx.config.apps.values())

    def packages(self, ctx: Context) -> list[str]:
        return ["flatpak"] if _flatpaks(ctx) else []

    def plan(self, ctx: Context) -> list[Change]:
        changes = []
        flatpaks = _flatpaks(ctx)
        if flatpaks and "flathub" not in output(["flatpak", "remotes", "--columns=name"]).split():
            argv = ["flatpak", "remote-add", "--system", "--if-not-exists", "flathub", FLATHUB]
            changes.append(Change("add the Flathub remote", partial(run, argv, root=True)))
        installed = set(output(["flatpak", "list", "--app", "--columns=application"]).split())
        missing = {name: app_id for name, app_id in flatpaks.items() if app_id not in installed}
        for name, app_id in missing.items():
            argv = ["flatpak", "install", "--system", "-y", "--noninteractive", "flathub", app_id]
            install = partial(run, argv, root=True)
            changes.append(_guarded(ctx, name, f"install {name} (flatpak {app_id})", install))
        if missing:
            ctx.note("New flatpak apps show up in the app menu after you log out and back in.")

        for name, app in ctx.config.apps.items():
            if app.deb and not ctx.apt.installed([app.deb.package]):
                url = app.deb.url.get(ctx.facts.arch)
                if url is None:
                    ctx.note(f"{name}: no .deb for {ctx.facts.arch} in apps.{name}.deb.url; skipped")
                else:
                    install = partial(_install_deb, ctx, app.deb, url)
                    changes.append(_guarded(ctx, name, f"install {name} (.deb)", install))
            if app.script and shutil.which(app.script.command) is None:
                install = partial(_run_script, app.script)
                changes.append(_guarded(ctx, name, f"install {name} (script {app.script.url})", install))
        return changes


def _flatpaks(ctx: Context) -> dict[str, str]:
    return {name: app.flatpak for name, app in ctx.config.apps.items() if app.flatpak}


def _guarded(ctx: Context, name: str, summary: str, install: Callable[[], object]) -> Change:
    """One app failing (a vendor site down, an unsupported release) shouldn't stop the
    rest of the run; report it at the end instead."""

    def apply() -> None:
        try:
            install()
        except (CommandError, OSError) as exc:
            print(f"        failed: {exc}")
            ctx.note(f"{name} was not installed ({exc}); rerun with -v for details.")

    return Change(summary, apply)


def _install_deb(ctx: Context, deb: Deb, url: str) -> None:
    # apt drops privileges to _apt to read local files, so keep them world-readable.
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp).chmod(0o755)
        path = Path(tmp) / f"{deb.package}.deb"
        path.write_bytes(fetch(url, timeout=600))
        path.chmod(0o644)
        ctx.apt.install([str(path)])


def _run_script(script: Script) -> None:
    run(["bash", "-s"], input=fetch(script.url).decode(), calls_sudo=True)
