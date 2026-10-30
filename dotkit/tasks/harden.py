"""Linux Mint debloat and hardening, by running scripts/mint/harden.sh.

The machine profile's `harden` answer (standard | aggressive) turns it on; config.yaml's
`harden.skip` leaves sections alone everywhere. One-time: it runs again when the
answer, the skip list or the script itself changes (or with --rerun harden).
"""

from __future__ import annotations

import hashlib
import re
from functools import partial
from pathlib import Path

from ..system import output, run
from .base import Change, Context, Task

_CHANGE = re.compile(r"^\s+~ (.*?)(?: \(preview\))?$")


class Harden(Task):
    name = "harden"
    summary = "Linux Mint: remove preinstalled bloat, harden the kernel, firewall and services"
    once = True

    def enabled(self, ctx: Context) -> bool:
        profile = ctx.config.profile
        return (
            profile is not None
            and profile.harden != "none"
            and ctx.facts.distro_id == "linuxmint"
            and not ctx.facts.wsl
        )

    def fingerprint(self, ctx: Context) -> object:
        return {
            "level": ctx.config.profile.harden if ctx.config.profile else "none",
            "skip": ctx.config.harden.skip,
            "script": hashlib.sha256(_script(ctx).read_bytes()).hexdigest(),
        }

    def plan(self, ctx: Context) -> list[Change]:
        # Without --apply the script only inspects the system and lists its changes.
        preview = output(_argv(ctx), any_exit=True)
        changes = [m.group(1) for line in preview.splitlines() if (m := _CHANGE.match(line))]
        if not changes:
            return []
        shown = "; ".join(changes[:4]) + (f"; +{len(changes) - 4} more" if len(changes) > 4 else "")
        summary = f"debloat and harden ({len(changes)} changes: {shown})"
        ctx.note("Every hardening change: scripts/mint/harden.sh --help. Reboot to load them all.")
        return [Change(summary, partial(run, [*_argv(ctx), "--apply", "--yes"]))]


def _script(ctx: Context) -> Path:
    return ctx.repo / "scripts" / "mint" / "harden.sh"


def _argv(ctx: Context) -> list[str]:
    argv = [str(_script(ctx))]
    if ctx.config.profile and ctx.config.profile.harden == "aggressive":
        argv.append("--aggressive")
    if ctx.config.harden.skip:
        argv += ["--skip", ",".join(ctx.config.harden.skip)]
    return argv
