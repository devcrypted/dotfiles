"""Install shells, hook bash/zsh rc files, and set the login shell."""

from __future__ import annotations

import pwd
import shutil
from functools import partial
from pathlib import Path

from ..fsops import BLOCK_START, backup, upsert_block, write_if_changed
from ..system import CommandError, run
from .base import Change, Context, Task

# rc file -> the init file it sources (both relative to $HOME).
RC_FILES = {
    "bash": (".bashrc", ".config/bash/init.bash"),
    "zsh": (".zshrc", ".config/zsh/init.zsh"),
}
ZSH_PLUGINS = ("zsh-autosuggestions", "zsh-syntax-highlighting")


class Shells(Task):
    name = "shells"
    summary = "Install shells, add a managed block to ~/.bashrc and ~/.zshrc, set login shell"

    def packages(self, ctx: Context) -> list[str]:
        shells = list(ctx.config.shells.install)
        return shells + list(ZSH_PLUGINS) if "zsh" in shells else shells

    def plan(self, ctx: Context) -> list[Change]:
        changes = [c for shell in ctx.config.shells.install if (c := _rc_change(ctx, shell))]
        want = ctx.config.shells.default
        if Path(pwd.getpwnam(ctx.facts.user).pw_shell).name != want:
            changes.append(Change(f"set login shell to {want}", partial(_chsh, ctx, want)))
        return changes


def _rc_change(ctx: Context, shell: str) -> Change | None:
    if shell not in RC_FILES:
        return None  # fish loads ~/.config/fish/conf.d/ by itself; config.fish stays local
    rc_name, init = RC_FILES[shell]
    rc = ctx.home / rc_name
    body = f'[ -r "$HOME/{init}" ] && . "$HOME/{init}"'

    if rc.is_symlink():
        # A symlinked rc file makes every tool that appends to it edit the target
        # (often this repo). Replace it with a real, machine-local file.
        summary = f"replace symlinked {ctx.show(rc)} with a local file (old one backed up)"
        return Change(summary, partial(_replace_symlink, ctx, rc, body, shell))

    current = rc.read_text() if rc.is_file() else _skeleton(shell)
    desired = upsert_block(current, body)
    if rc.is_file() and desired == current:
        return None
    verb = "update" if BLOCK_START in current else "add"
    return Change(f"{verb} dotfiles block in {ctx.show(rc)}", partial(write_if_changed, rc, desired))


def _replace_symlink(ctx: Context, rc: Path, body: str, shell: str) -> None:
    backup(rc, ctx.home, ctx.backup_dir)
    ctx.note(f"Replaced files were backed up under {ctx.show(ctx.backup_dir)}")
    write_if_changed(rc, upsert_block(_skeleton(shell), body))


def _skeleton(shell: str) -> str:
    """Distro default rc (e.g. /etc/skel/.bashrc) to start a new rc file from."""
    skel = Path("/etc/skel") / RC_FILES[shell][0]
    return skel.read_text() if skel.is_file() else ""


def _chsh(ctx: Context, shell: str) -> None:
    path = shutil.which(shell)
    if path is None:
        raise CommandError(["chsh"], 1, f"{shell} is not installed (run the packages task)")
    if path not in Path("/etc/shells").read_text().split():
        run(["tee", "-a", "/etc/shells"], root=True, input=f"{path}\n")
    run(["chsh", "-s", path, ctx.facts.user], root=True)
    ctx.note(f"Login shell is now {shell}; it applies to new logins.")
