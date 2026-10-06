"""An ed25519 SSH key for this machine."""

from __future__ import annotations

from functools import partial

from ..system import run
from .base import Change, Context, Task


class Ssh(Task):
    name = "ssh"
    summary = "Generate ~/.ssh/id_ed25519 if no key exists yet"
    once = True

    def enabled(self, ctx: Context) -> bool:
        return ctx.config.ssh.generate_key

    def packages(self, ctx: Context) -> list[str]:
        return ["openssh-client"]

    def plan(self, ctx: Context) -> list[Change]:
        key = ctx.home / ".ssh" / "id_ed25519"
        if key.exists():
            return []
        return [Change(f"generate {ctx.show(key)}", partial(_keygen, ctx))]


def _keygen(ctx: Context) -> None:
    ssh_dir = ctx.home / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key = ssh_dir / "id_ed25519"
    comment = ctx.config.user.email or f"{ctx.facts.user}@dotfiles"
    run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(key)])
    ctx.note(f"New SSH public key: {ctx.show(key)}.pub (add it to GitHub with `gh ssh-key add`)")
