"""Language runtimes and CLI tools via mise (https://mise.jdx.dev)."""

from __future__ import annotations

import shutil
import tomllib
from functools import partial

from ..system import output, run
from .base import Change, Context, Task

REPO = "mise"
KEY_URL = "https://mise.jdx.dev/gpg-key.pub"


class Mise(Task):
    name = "mise"
    summary = "Install mise and sync global `tools`; tools removed from config are uninstalled"

    def enabled(self, ctx: Context) -> bool:
        return bool(ctx.config.tools or ctx.state.get("mise_tools"))

    def plan(self, ctx: Context) -> list[Change]:
        changes = []
        if shutil.which("mise") is None:
            changes.append(Change("install mise from its apt repo", partial(_install_mise, ctx)))

        current = _global_tools(ctx)
        for tool, version in ctx.config.tools.items():
            if current.get(tool) != version:
                argv = ["mise", "use", "--global", "--yes", f"{tool}@{version}"]
                changes.append(Change(f"use {tool}@{version}", partial(run, argv)))

        # Only remove tools this installer added; anything set up by hand is left alone.
        for tool in sorted(set(ctx.state.get("mise_tools", [])) - ctx.config.tools.keys()):
            if tool in current:
                argv = ["mise", "unuse", "--global", "--yes", tool]
                changes.append(Change(f"remove {tool}", partial(run, argv)))

        if not changes and _has_missing():
            argv = ["mise", "install", "--yes"]
            changes.append(Change("install missing tool versions", partial(run, argv)))
        return changes

    def commit(self, ctx: Context) -> None:
        ctx.state.put("mise_tools", sorted(ctx.config.tools))


def _install_mise(ctx: Context) -> None:
    line = ctx.apt.source_line(REPO, "https://mise.jdx.dev/deb", "stable", "main")
    if not ctx.apt.repo_current(REPO, line):
        ctx.apt.add_repo(REPO, KEY_URL, line)
    ctx.apt.install(["mise"])


def _global_tools(ctx: Context) -> dict[str, str]:
    path = ctx.home / ".config" / "mise" / "config.toml"
    if not path.is_file():
        return {}
    tools = tomllib.loads(path.read_text()).get("tools", {})
    return {k: v if isinstance(v, str) else repr(v) for k, v in tools.items()}


def _has_missing() -> bool:
    if shutil.which("mise") is None:
        return False
    return output(["mise", "ls", "--global", "--missing", "--json"]).strip() not in ("", "{}")
