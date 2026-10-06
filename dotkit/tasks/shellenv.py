"""Generated env/PATH/alias/abbr snippets in ~/.config/dotfiles/."""

from __future__ import annotations

from functools import partial

from ..fsops import write_if_changed
from ..render import generated_files
from .base import Change, Context, Task


class ShellEnv(Task):
    name = "shellenv"
    summary = "Render `aliases`, `env`, `path` and `mask` into bash/zsh and fish snippets"

    def plan(self, ctx: Context) -> list[Change]:
        directory = ctx.home / ".config" / "dotfiles"
        changes = []
        for name, content in generated_files(ctx.config, ctx.home).items():
            path = directory / name
            if not path.is_file() or path.read_text() != content:
                changes.append(Change(f"write {ctx.show(path)}", partial(write_if_changed, path, content)))
        return changes
