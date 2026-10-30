"""CUDA toolkit from NVIDIA's repo, on machines with an NVIDIA GPU (WSL included)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from functools import partial
from pathlib import Path

from ..apt import STATUS_FD, apt_status
from ..system import CommandError, fetch, output, run
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
        # An interrupted install has its packages downloaded already: finish it rather
        # than starting over.
        broken = interrupted()
        if broken:
            summary = f"finish the interrupted CUDA install ({len(broken)} package(s); no new downloads)"
            return [Change(summary, partial(_repair, ctx))]
        # Any working nvcc counts, however it was installed (NVIDIA's repo, a versioned
        # cuda-toolkit-X-Y package, Ubuntu's nvidia-cuda-toolkit or the runfile).
        if nvcc_version():
            return []
        return [Change("install cuda-toolkit (several GB)", partial(_install, ctx))]


def nvcc_version() -> str:
    """Version of the first nvcc that actually runs ("13.4"), or "" when there is none."""
    candidates = [
        shutil.which("nvcc"),
        "/usr/local/cuda/bin/nvcc",
        *sorted(map(str, Path("/usr/local").glob("cuda-*/bin/nvcc")), reverse=True),
        "/usr/bin/nvcc",
    ]
    for path in dict.fromkeys(c for c in candidates if c):
        if os.access(path, os.X_OK):
            match = re.search(r"release (\d+\.\d+)", output([path, "--version"]))
            if match:
                return match.group(1)
    return ""


def interrupted() -> list[str]:
    """CUDA packages dpkg left unpacked, half-configured or needing reinstall."""
    lines = output(
        ["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Package}\n", "cuda-*", "nvidia-cuda-*"], any_exit=True
    )
    broken = []
    for line in lines.splitlines():
        # "${db:Status-Abbrev}" is 3 characters (desired, state, error), e.g. "iU ".
        status, name = line[:3], line[3:].strip()
        if name and (status[1:2] in ("U", "F", "H", "W", "t") or status[2:3] == "R"):
            broken.append(name)
    return broken


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
    _verify(ctx)


def _repair(ctx: Context) -> None:
    run(["dpkg", "--configure", "-a"], root=True, env={"DEBIAN_FRONTEND": "noninteractive"})
    # apt reuses the .debs already in /var/cache/apt/archives, so this only downloads
    # what an interrupted download never finished.
    run(
        ["apt-get", *STATUS_FD, "install", "-f", "-y"],
        root=True,
        env={"DEBIAN_FRONTEND": "noninteractive"},
        progress=apt_status,
    )
    if not nvcc_version():
        _install(ctx)
        return
    _verify(ctx)


def _verify(ctx: Context) -> None:
    version = nvcc_version()
    if not version:
        raise CommandError(
            ["nvcc", "--version"], 1, "cuda-toolkit is installed but no working nvcc was found"
        )
    ctx.note(f"CUDA {version} is in /usr/local/cuda; open a new shell to get nvcc on PATH.")
