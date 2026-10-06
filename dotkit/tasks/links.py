"""Symlink every file under home/<module>/ into $HOME, backing up whatever was there."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from ..config import ConfigError
from ..fsops import backup, ensure_real_dir, link_target
from .base import Change, Context, Task


class Links(Task):
    name = "links"
    summary = "Symlink each file in home/<module>/ into $HOME; back up and prune"

    def plan(self, ctx: Context) -> list[Change]:
        desired = desired_links(ctx)
        changes = []
        for target, source in desired.items():
            if link_target(target) == source:
                continue
            exists = target.exists() or target.is_symlink()
            summary = f"link {ctx.show(target)}" + (" (existing one backed up)" if exists else "")
            changes.append(Change(summary, partial(_link, ctx, target, source)))

        for target in sorted(_previously_managed(ctx) - desired.keys()):
            if _points_into(target, ctx.repo):
                summary = f"unlink {ctx.show(target)} (no longer in the repo or config)"
                changes.append(Change(summary, target.unlink))
        return changes

    def commit(self, ctx: Context) -> None:
        ctx.state.put("links", sorted(str(t) for t in desired_links(ctx)))


def desired_links(ctx: Context) -> dict[Path, Path]:
    """Map of target path in $HOME -> source file in the repo, for enabled modules."""
    links: dict[Path, Path] = {}
    owner: dict[Path, str] = {}
    for module in ctx.config.enabled_modules:
        root = ctx.repo / "home" / module
        for source in sorted(root.rglob("*")):
            if source.is_dir() and not source.is_symlink():
                continue
            target = ctx.home / source.relative_to(root)
            if target in links:
                raise ConfigError(
                    f"{ctx.show(target)} is provided by both modules {owner[target]!r} and {module!r}"
                )
            links[target] = source
            owner[target] = module
    return links


def _previously_managed(ctx: Context) -> set[Path]:
    """Links recorded by earlier runs, plus top-level repo links left by GNU Stow."""
    recorded = {Path(p) for p in ctx.state.get("links", [])}
    stowed = {p for p in ctx.home.iterdir() if _points_into(p, ctx.repo)}
    return recorded | stowed


def _points_into(path: Path, directory: Path) -> bool:
    """True for a symlink to something *inside* ``directory`` (not to the directory itself)."""
    target = link_target(path)
    return target is not None and target != directory and target.is_relative_to(directory)


def _link(ctx: Context, target: Path, source: Path) -> None:
    # Fix symlinked parents first, so a backup never moves a file that lives elsewhere.
    ensure_real_dir(target.parent, ctx.home, ctx.backup_dir)
    if target.exists() or target.is_symlink():
        backup(target, ctx.home, ctx.backup_dir)
        ctx.note(f"Replaced files were backed up under {ctx.show(ctx.backup_dir)}")
    target.symlink_to(source)
