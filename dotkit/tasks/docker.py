"""Docker Engine from download.docker.com, plus docker group membership."""

from __future__ import annotations

import grp
import pwd
import shutil
from functools import partial

from ..system import output, run
from .base import Change, Context, Task

REPO = "docker"
PACKAGES = ["docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"]


class Docker(Task):
    name = "docker"
    summary = "Install Docker Engine unless a docker CLI exists, ensure buildx, add you to `docker`"

    def enabled(self, ctx: Context) -> bool:
        return ctx.config.docker.enabled

    def plan(self, ctx: Context) -> list[Change]:
        changes = []
        # An existing docker (distro docker.io, or Docker Desktop on WSL) is respected:
        # swapping engines would remove packages and disrupt running containers.
        if shutil.which("docker") is None:
            changes.append(Change("install Docker Engine (includes buildx)", partial(_install, ctx)))
        elif not _has_buildx():
            package = _buildx_package(ctx)
            if package:
                changes.append(
                    Change(f"install {package} (docker buildx)", partial(ctx.apt.install, [package]))
                )
            else:
                ctx.note("docker buildx is missing; no apt package offers it (see docs.docker.com/build)")
        if not _in_docker_group(ctx.facts.user):
            changes.append(Change(f"add {ctx.facts.user} to the docker group", partial(_join_group, ctx)))
        return changes


def _has_buildx() -> bool:
    return bool(output(["docker", "buildx", "version"]).strip())


def _buildx_package(ctx: Context) -> str | None:
    """The buildx package that matches how Docker itself was installed.

    Ubuntu's `docker-buildx` depends on docker.io and Debian 12 doesn't have it, so it
    is only used when no docker.com engine is present. Never list it in `packages`.
    """
    if ctx.apt.installed(["docker-ce-cli"]):
        return "docker-buildx-plugin"
    return "docker-buildx" if ctx.apt.available("docker-buildx") else None


def _install(ctx: Context) -> None:
    url = "https://download.docker.com/linux/{distro}"
    line = ctx.apt.source_line(REPO, url, "{codename}", "stable")
    if not ctx.apt.repo_current(REPO, line):
        ctx.apt.add_repo(REPO, f"{url}/gpg", line)
    ctx.apt.install(PACKAGES)


def _in_docker_group(user: str) -> bool:
    try:
        group = grp.getgrnam("docker")
    except KeyError:
        return False
    return user in group.gr_mem or pwd.getpwnam(user).pw_gid == group.gr_gid


def _join_group(ctx: Context) -> None:
    run(["groupadd", "--force", "docker"], root=True)
    run(["usermod", "--append", "--groups", "docker", ctx.facts.user], root=True)
    ctx.note("You were added to the docker group: log out and back in for it to apply.")
