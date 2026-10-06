"""Process execution, sudo handling and host detection."""

from __future__ import annotations

import os
import platform
import pwd
import shlex
import subprocess
import threading
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_DEBIAN_VERSIONS = {"bullseye": "11", "bookworm": "12", "trixie": "13"}
_ARCHES = {"x86_64": "amd64", "aarch64": "arm64"}

verbose = False


class CommandError(Exception):
    """A command exited non-zero."""

    def __init__(self, argv: Sequence[str], returncode: int, output: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.output = output
        super().__init__(f"`{shlex.join(self.argv)}` exited with {returncode}")


class UnsupportedSystem(Exception):
    """The host is not something the installer knows how to manage."""


def run(
    argv: Sequence[str],
    *,
    root: bool = False,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` and return the result with stdout/stderr captured as text.

    ``root`` runs it through sudo (unless we already are root); ``env`` adds
    variables in a way that survives sudo's environment reset. Output is streamed
    instead of captured when ``verbose`` is set.
    """
    cmd = list(argv)
    if env:
        cmd = ["env", *(f"{k}={v}" for k, v in env.items()), *cmd]
    if root and os.geteuid() != 0:
        sudo.ensure()
        cmd = ["sudo", *cmd]
    if verbose:
        print(f"      $ {shlex.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        input=input,
        cwd=cwd,
        text=True,
        stdout=None if verbose else subprocess.PIPE,
        stderr=None if verbose else subprocess.STDOUT,
        check=False,
    )
    if check and result.returncode != 0:
        raise CommandError(cmd, result.returncode, result.stdout or "")
    return result


def output(argv: Sequence[str], *, any_exit: bool = False) -> str:
    """Run a read-only query and return its stdout.

    On a non-zero exit this returns '' unless ``any_exit`` is set (some tools, such
    as dpkg-query, still print useful results when they fail for one argument).
    """
    try:
        result = subprocess.run(list(argv), text=True, capture_output=True, check=False)
    except FileNotFoundError:
        return ""
    return result.stdout if result.returncode == 0 or any_exit else ""


def fetch(url: str, timeout: int = 60) -> bytes:
    """Download ``url``. Some CDNs reject urllib's default User-Agent, so send our own."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "dotkit (+https://github.com/devcrypted/dotfiles)"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


class _Sudo:
    """Ask for the sudo password at most once per run, then keep the ticket fresh."""

    def __init__(self) -> None:
        self._ready = False
        self._stop = threading.Event()

    def ensure(self) -> None:
        if self._ready:
            return
        if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
            raise CommandError(["sudo", "-v"], 1, "could not obtain sudo privileges")
        self._ready = True
        threading.Thread(target=self._keepalive, daemon=True).start()

    def _keepalive(self) -> None:
        while not self._stop.wait(60):
            subprocess.run(["sudo", "-n", "-v"], check=False, capture_output=True)

    def stop(self) -> None:
        self._stop.set()


sudo = _Sudo()


@dataclass(frozen=True)
class Facts:
    """What we know about the host, detected once per run."""

    distro: str  # vendor family used for upstream repos: "ubuntu" or "debian"
    distro_id: str  # raw os-release ID, e.g. "linuxmint"
    codename: str  # upstream codename, e.g. "noble" on Linux Mint 22
    version: str  # upstream major version for Debian ("12"), else ""
    arch: str  # dpkg architecture, e.g. "amd64"
    user: str
    wsl: bool
    nvidia_gpu: bool

    @property
    def pretty(self) -> str:
        name = self.distro if self.distro_id == self.distro else f"{self.distro_id}/{self.distro}"
        return f"{name} {self.codename} {self.arch}{' (WSL)' if self.wsl else ''}"

    def template(self, text: str) -> str:
        """Fill {distro}, {codename}, {version} and {arch} placeholders."""
        return text.format(distro=self.distro, codename=self.codename, version=self.version, arch=self.arch)


def detect(os_release: Path = Path("/etc/os-release")) -> Facts:
    info = parse_os_release(os_release.read_text() if os_release.exists() else "")
    candidates = [info.get("ID", ""), *info.get("ID_LIKE", "").split()]
    family = next((c for c in candidates if c in ("ubuntu", "debian")), None)
    if family is None:
        raise UnsupportedSystem(
            f"unsupported distro {info.get('ID', 'unknown')!r}: only Debian and Ubuntu "
            "(including derivatives such as Mint and WSL Ubuntu) are supported"
        )
    if family == "ubuntu":
        codename = info.get("UBUNTU_CODENAME") or info.get("VERSION_CODENAME", "")
    else:
        codename = info.get("DEBIAN_CODENAME") or info.get("VERSION_CODENAME", "")
    return Facts(
        distro=family,
        distro_id=info.get("ID", family),
        codename=codename,
        version=_DEBIAN_VERSIONS.get(codename, "") if family == "debian" else "",
        arch=output(["dpkg", "--print-architecture"]).strip()
        or _ARCHES.get(platform.machine(), platform.machine()),
        user=pwd.getpwuid(os.getuid()).pw_name,
        wsl="microsoft" in _read("/proc/sys/kernel/osrelease").lower(),
        nvidia_gpu=has_nvidia_gpu(),
    )


def parse_os_release(text: str) -> dict[str, str]:
    info = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.startswith("#"):
            info[key.strip()] = value.strip().strip("'\"")
    return info


def has_nvidia_gpu(pci: Path = Path("/sys/bus/pci/devices")) -> bool:
    """True when a PCI display controller (class 0x03xxxx) from NVIDIA (0x10de) exists."""
    if not pci.is_dir():
        return False
    return any(
        _read(dev / "vendor").strip() == "0x10de" and _read(dev / "class").startswith("0x03")
        for dev in pci.iterdir()
    )


def _read(path: str | Path) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""
