"""System packages from the distro archive."""

from __future__ import annotations

from .base import Change, Context, Task


class Packages(Task):
    name = "packages"
    summary = "Install `packages` plus whatever enabled tasks need, in one apt transaction"

    def plan(self, ctx: Context) -> list[Change]:
        from . import TASKS  # late import: the registry imports this module

        wanted = list(ctx.config.packages)
        for task in TASKS:
            if task.enabled(ctx):
                wanted += task.packages(ctx)
        missing = ctx.apt.missing(wanted)
        if not missing:
            return []
        summary = f"install {len(missing)} package(s): {' '.join(missing)}"
        return [Change(summary, lambda: ctx.apt.install(missing))]
