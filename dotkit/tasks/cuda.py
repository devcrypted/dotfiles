"""CUDA toolkit from NVIDIA's repo, on machines with an NVIDIA GPU (WSL included)."""

from __future__ import annotations

import tempfile
from functools import partial
from pathlib import Path

from ..system import CommandError, fetch, run
from .base import Change, Context, Task

REPOS = "https://developer.download.nvidia.com/compute/cuda/repos"
# NVIDIA names its Ubuntu repos by release number; Mint & co. report the Ubuntu codename.
UBUNTU_RELEASES = {"jammy": "2204", "noble": "2404", "resolute": "2604"}
ARCHES = {"amd64": "x86_64", "arm64": "sbsa"}


class Cuda(Task):
    name = "cuda"
    summary = "Install the CUDA toolkit (nvcc, libraries) from NVIDIA's apt repo"

    def enabled(self, ctx: Context) -> bool:
        # resolve() only keeps `nvidia.cuda` on when the profile wants the GPU and one exists.
        return ctx.config.nvidia.cuda

    def plan(self, ctx: Context) -> list[Change]:
        if ctx.apt.installed(["cuda-toolkit"]):
            return []
        return [Change("install cuda-toolkit (several GB)", partial(_install, ctx))]


def repo_url(ctx: Context) -> str:
    f = ctx.facts
    if f.wsl and f.distro == "ubuntu":
        name = "wsl-ubuntu"
    elif f.distro == "ubuntu" and f.codename in UBUNTU_RELEASES:
        name = f"ubuntu{UBUNTU_RELEASES[f.codename]}"
    elif f.distro == "debian" and f.version:
        name = f"debian{f.version}"
    else:
        name = ""
    if not name or f.arch not in ARCHES:
        raise CommandError(["cuda"], 1, f"NVIDIA has no CUDA repo for {f.pretty}")
    return f"{REPOS}/{name}/{ARCHES[f.arch]}"


def add_repo(ctx: Context) -> None:
    """Install NVIDIA's cuda-keyring package, which adds the repo and its signing key."""
    if ctx.apt.installed(["cuda-keyring"]):
        return
    with tempfile.TemporaryDirectory() as tmp:
        keyring = Path(tmp) / "cuda-keyring.deb"
        keyring.write_bytes(fetch(f"{repo_url(ctx)}/cuda-keyring_1.1-1_all.deb"))
        run(["dpkg", "-i", str(keyring)], root=True)
    ctx.apt.update()


def _install(ctx: Context) -> None:
    add_repo(ctx)
    ctx.apt.install(["cuda-toolkit"])
    ctx.note("CUDA installed in /usr/local/cuda; open a new shell to get nvcc on PATH.")
