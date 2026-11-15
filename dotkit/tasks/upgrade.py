"""Full system upgrade: once on a fresh machine, and on every `./install.sh upgrade`."""

from __future__ import annotations

from .base import Change, Context, Task


class Upgrade(Task):
    name = "upgrade"
    summary = "apt full-upgrade on the first run and on `./install.sh upgrade`"
    once = True

    def enabled(self, ctx: Context) -> bool:
        return ctx.config.upgrade

    def plan(self, ctx: Context) -> list[Change]:
        return [Change("apt-get full-upgrade", ctx.apt.upgrade)]
