"""`./install.sh reinstall NAME...`: install an app, tool or package again from scratch."""

from __future__ import annotations

from collections.abc import Iterable
from functools import partial

from .config import ConfigError
from .system import run
from .tasks import Change, Context
from .tasks.apps import install_deb, install_flatpak, run_script


def plan(ctx: Context, names: Iterable[str]) -> list[Change]:
    """Changes that reinstall each name: an entry in `apps`, a mise tool or an apt
    package, as resolved for this machine."""
    config = ctx.config
    changes: list[Change] = []
    for name in names:
        app = config.apps.get(name)
        if app:
            packages = [*app.apt, *(app.apt_repo.packages if app.apt_repo else ())]
            changes += [_apt(ctx, package) for package in packages]
            changes += [_mise(tool) for tool in app.mise]
            if app.flatpak:
                summary = f"reinstall {name} (flatpak {app.flatpak})"
                changes.append(Change(summary, partial(install_flatpak, app.flatpak, reinstall=True)))
            url = app.deb.url.get(ctx.facts.arch) if app.deb else None
            if app.deb and url:
                changes.append(Change(f"reinstall {name} (.deb)", partial(install_deb, ctx, app.deb, url)))
            if app.script:
                summary = f"reinstall {name} (script {app.script.url})"
                changes.append(Change(summary, partial(run_script, app.script)))
        elif name in config.tools:
            changes.append(_mise(name))
        elif name in config.packages:
            changes.append(_apt(ctx, name))
        else:
            raise ConfigError(
                f"reinstall: {name!r} is not an app, tool or package in this machine's config "
                "(see apps, tools, personas and packages in config.yaml)"
            )
    return changes


def _apt(ctx: Context, package: str) -> Change:
    return Change(f"reinstall {package} (apt)", partial(ctx.apt.install, [package], reinstall=True))


def _mise(tool: str) -> Change:
    argv = ["mise", "install", "--force", "--yes", tool]
    return Change(f"reinstall {tool} (mise)", partial(run, argv))
