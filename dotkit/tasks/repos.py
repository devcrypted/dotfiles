"""Third-party apt repositories declared under `apt_repos`."""

from __future__ import annotations

from functools import partial

from .base import Change, Context, Task


class Repos(Task):
    name = "repos"
    summary = "Add each `apt_repos` entry (signed-by keyring) and install its packages"

    def enabled(self, ctx: Context) -> bool:
        return bool(ctx.config.apt_repos or ctx.state.get("apt_repos"))

    def plan(self, ctx: Context) -> list[Change]:
        apt, changes = ctx.apt, []
        for name, repo in ctx.config.apt_repos.items():
            line = apt.source_line(name, repo.url, repo.suite, repo.components)
            if not apt.repo_current(name, line):
                changes.append(Change(f"add apt repo {name}", partial(apt.add_repo, name, repo.key, line)))
            missing = apt.missing(repo.packages)
            if missing:
                summary = f"install from {name}: {' '.join(missing)}"
                changes.append(Change(summary, partial(apt.install, missing)))
        # Repos we added earlier but that were removed from the config. Their packages
        # stay installed: removing software is a decision to make by hand.
        for name in sorted(set(ctx.state.get("apt_repos", [])) - ctx.config.apt_repos.keys()):
            changes.append(Change(f"remove apt repo {name}", partial(apt.remove_repo, name)))
        return changes

    def commit(self, ctx: Context) -> None:
        ctx.state.put("apt_repos", sorted(ctx.config.apt_repos))
