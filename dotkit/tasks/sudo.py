"""Opt-in passwordless sudo through a validated /etc/sudoers.d drop-in."""

from __future__ import annotations

import subprocess
import tempfile
from functools import partial

from ..system import run
from .base import Change, Context, Task

DROP_IN = "/etc/sudoers.d/90-dotfiles"


class Sudo(Task):
    name = "sudo"
    summary = "Manage passwordless sudo (`sudo_nopasswd`) via /etc/sudoers.d/90-dotfiles"

    def enabled(self, ctx: Context) -> bool:
        return ctx.config.sudo_nopasswd or bool(ctx.state.get("sudoers"))

    def plan(self, ctx: Context) -> list[Change]:
        # /etc/sudoers.d isn't readable without root, so "already passwordless" is the
        # check; that way a no-op run never prompts for a password.
        if ctx.config.sudo_nopasswd:
            if ctx.state.get("sudoers") and _passwordless():
                return []
            return [Change("allow passwordless sudo", partial(_install, ctx))]
        return [Change("remove passwordless sudo drop-in", partial(_remove, ctx))]


def _passwordless() -> bool:
    return subprocess.run(["sudo", "-n", "true"], capture_output=True, check=False).returncode == 0


def _install(ctx: Context) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sudoers") as tmp:
        tmp.write(f"{ctx.facts.user} ALL=(ALL) NOPASSWD: ALL\n")
        tmp.flush()
        run(["visudo", "--check", "--file", tmp.name])  # never install a file that breaks sudo
        run(["install", "-m", "0440", "-o", "root", "-g", "root", tmp.name, DROP_IN], root=True)
    ctx.state.put("sudoers", True)


def _remove(ctx: Context) -> None:
    run(["rm", "-f", DROP_IN], root=True)
    ctx.state.put("sudoers", False)
