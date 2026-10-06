"""NVIDIA driver and, optionally, the container toolkit for Docker GPU access."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import asdict
from functools import partial
from pathlib import Path

from ..system import CommandError, fetch, output, run
from .base import Change, Context, Task

TOOLKIT_REPO = "nvidia-container-toolkit"
TOOLKIT_URL = "https://nvidia.github.io/libnvidia-container"
CUDA_REPO = "https://developer.download.nvidia.com/compute/cuda/repos/debian{version}/x86_64"


class Nvidia(Task):
    name = "nvidia"
    summary = "Install the NVIDIA driver (open or proprietary) and the container toolkit"
    once = True

    def enabled(self, ctx: Context) -> bool:
        setting = ctx.config.nvidia.enabled
        if setting == "auto":
            # WSL uses the Windows host driver; installing a Linux one there breaks CUDA.
            return ctx.facts.nvidia_gpu and not ctx.facts.wsl
        return setting

    def packages(self, ctx: Context) -> list[str]:
        if ctx.facts.distro == "ubuntu":
            return ["ubuntu-drivers-common"]
        return ["software-properties-common", f"linux-headers-{os.uname().release}"]

    def fingerprint(self, ctx: Context) -> object:
        return asdict(ctx.config.nvidia)

    def plan(self, ctx: Context) -> list[Change]:
        cfg, changes = ctx.config.nvidia, []
        if not _driver_installed(ctx, cfg.flavor):
            install = _install_ubuntu if ctx.facts.distro == "ubuntu" else _install_debian
            changes.append(Change(f"install NVIDIA {cfg.flavor} driver", partial(install, ctx)))

        if cfg.container_toolkit:
            if not ctx.apt.installed(["nvidia-container-toolkit"]):
                changes.append(Change("install nvidia-container-toolkit", partial(_install_toolkit, ctx)))
            if shutil.which("docker") and "nvidia" not in _read("/etc/docker/daemon.json"):
                changes.append(Change("register the nvidia runtime with Docker", _configure_docker))
        return changes


def _driver_installed(ctx: Context, flavor: str) -> bool:
    installed = ctx.apt.installed(["nvidia-driver-*", "nvidia-open", "cuda-drivers"])
    is_open = [name.endswith("-open") for name in installed]
    return any(is_open) if flavor == "open" else not all(is_open)


def _install_ubuntu(ctx: Context) -> None:
    devices = output(["ubuntu-drivers", "devices"])
    match = re.search(r"nvidia-driver-(\d+)(?:-open)?\b.*\brecommended\b", devices)
    if match is None:
        raise CommandError(["ubuntu-drivers", "devices"], 1, "no recommended NVIDIA driver found")
    suffix = "-open" if ctx.config.nvidia.flavor == "open" else ""
    run(["ubuntu-drivers", "install", f"nvidia:{match.group(1)}{suffix}"], root=True)
    ctx.note("NVIDIA driver installed: reboot to load it.")


def _install_debian(ctx: Context) -> None:
    if ctx.facts.arch != "amd64" or not ctx.facts.version:
        raise CommandError(["nvidia"], 1, f"no CUDA repo for {ctx.facts.pretty}")
    repo = CUDA_REPO.format(version=ctx.facts.version)
    with tempfile.TemporaryDirectory() as tmp:
        keyring = Path(tmp) / "cuda-keyring.deb"
        keyring.write_bytes(fetch(f"{repo}/cuda-keyring_1.1-1_all.deb"))
        run(["dpkg", "-i", str(keyring)], root=True)
    run(["add-apt-repository", "-y", "contrib"], root=True)
    ctx.apt.update()
    ctx.apt.install(["nvidia-open" if ctx.config.nvidia.flavor == "open" else "cuda-drivers"])
    ctx.note("NVIDIA driver installed: reboot to load it (with Secure Boot, enroll the DKMS MOK key).")


def _install_toolkit(ctx: Context) -> None:
    line = ctx.apt.source_line(TOOLKIT_REPO, f"{TOOLKIT_URL}/stable/deb/{{arch}}", "/")
    if not ctx.apt.repo_current(TOOLKIT_REPO, line):
        ctx.apt.add_repo(TOOLKIT_REPO, f"{TOOLKIT_URL}/gpgkey", line)
    ctx.apt.install(["nvidia-container-toolkit"])


def _configure_docker() -> None:
    run(["nvidia-ctk", "runtime", "configure", "--runtime=docker"], root=True)
    if Path("/run/systemd/system").is_dir():
        run(["systemctl", "restart", "docker"], root=True)


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""
