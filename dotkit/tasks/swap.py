"""A swap file for machines that have no swap at all."""

from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path

from .. import system
from ..system import output, run
from .base import Change, Context, Task

SWAPFILE = Path("/swapfile")
FSTAB = Path("/etc/fstab")
_GIB = 1024**3
_HEADROOM_GB = 2  # disk that must stay free after the swap file is made


class Swap(Task):
    name = "swap"
    summary = "Create and enable a swap file when the machine has no swap (`swap`)"

    def enabled(self, ctx: Context) -> bool:
        # Containers share the host's swap and WSL manages its own (.wslconfig).
        return ctx.config.swap.enabled and not ctx.facts.wsl and not system.in_container()

    def plan(self, ctx: Context) -> list[Change]:
        if system.swaps():
            return []
        if SWAPFILE.exists():
            summary = f"enable the existing {SWAPFILE} now and at boot"
            return [Change(summary, _enable)]
        gb = swap_gb(ctx.config.swap.size, system.ram_gb())
        if _root_fs() == "btrfs":
            ctx.note("swap: skipped, / is btrfs (see `btrfs filesystem mkswapfile`)")
            return []
        if _free_bytes() < (gb + _HEADROOM_GB) * _GIB:
            ctx.note(f"swap: skipped, not enough free disk for a {gb}G swap file (set swap.size)")
            return []
        summary = f"create a {gb}G swap file at {SWAPFILE} and enable it now and at boot"
        return [Change(summary, partial(_create, gb))]


def swap_gb(size: str, ram_gb: int) -> int:
    """Swap size in GiB: ``size`` when given, else by RAM (small machines need it most)."""
    if size != "auto":
        return int(size.rstrip("G"))
    if ram_gb <= 2:
        return max(2, 2 * ram_gb)
    return ram_gb if ram_gb <= 8 else 4


def fstab_line(fstab: str) -> str | None:
    """The line to append to /etc/fstab, or None when the swap file is already listed."""
    if any(line.split()[:1] == [str(SWAPFILE)] for line in fstab.splitlines()):
        return None
    return f"{SWAPFILE} none swap sw 0 0\n"


def _create(gb: int) -> None:
    path = str(SWAPFILE)
    # fallocate is instant; filesystems that can't use such a file for swap need dd.
    if run(["fallocate", "-l", f"{gb}G", path], root=True, check=False).returncode != 0:
        run(["dd", "if=/dev/zero", f"of={path}", "bs=1M", f"count={gb * 1024}"], root=True)
    run(["chmod", "600", path], root=True)
    run(["mkswap", path], root=True)
    _enable()


def _enable() -> None:
    run(["swapon", str(SWAPFILE)], root=True)
    line = fstab_line(FSTAB.read_text())
    if line:
        run(["tee", "-a", str(FSTAB)], root=True, input=line)


def _root_fs() -> str:
    return output(["findmnt", "-n", "-o", "FSTYPE", "/"]).strip()


def _free_bytes() -> int:
    return shutil.disk_usage("/").free
