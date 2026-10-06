"""Git identity, kept in the machine-local ~/.gitconfig.

Shared settings live in ~/.config/git/config (linked from home/git/). Keeping the
identity and tool-written sections such as `gh auth setup-git` in ~/.gitconfig means
tools can rewrite that file freely without touching the repo.
"""

from __future__ import annotations

from functools import partial

from ..system import output, run
from .base import Change, Context, Task


class Git(Task):
    name = "git"
    summary = "Write `user.name`/`user.email` into the machine-local ~/.gitconfig"

    def enabled(self, ctx: Context) -> bool:
        return bool(ctx.config.user.name or ctx.config.user.email)

    def packages(self, ctx: Context) -> list[str]:
        return ["git"]

    def plan(self, ctx: Context) -> list[Change]:
        gitconfig = str(ctx.home / ".gitconfig")
        changes = []
        for key, value in (("user.name", ctx.config.user.name), ("user.email", ctx.config.user.email)):
            current = output(["git", "config", "--file", gitconfig, "--get", key]).strip()
            if value and current != value:
                argv = ["git", "config", "--file", gitconfig, key, value]
                changes.append(Change(f"set git {key} = {value}", partial(run, argv)))
        return changes
