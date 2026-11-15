from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import FACTS

from dotkit import system
from dotkit.config import Config, Swap
from dotkit.tasks import swap
from dotkit.tasks.swap import Swap as SwapTask
from dotkit.tasks.swap import swap_gb

GIB = 1024**3


@pytest.fixture
def ctx(make_ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(swap.system, "in_container", lambda: False)
    monkeypatch.setattr(swap.system, "swaps", lambda: [])
    monkeypatch.setattr(swap.system, "ram_gb", lambda: 4)
    monkeypatch.setattr(swap, "_root_fs", lambda: "ext4")
    monkeypatch.setattr(swap, "_free_bytes", lambda: 100 * GIB)
    monkeypatch.setattr(swap, "SWAPFILE", tmp_path / "swapfile")
    return make_ctx(Config(swap=Swap(enabled=True)))


@pytest.mark.parametrize(("ram", "expected"), [(0, 2), (1, 2), (2, 4), (4, 4), (8, 8), (16, 4), (64, 4)])
def test_auto_size_follows_ram(ram, expected):
    assert swap_gb("auto", ram) == expected


def test_explicit_size_wins():
    assert swap_gb("6G", 64) == 6


def test_creates_a_swap_file_when_the_machine_has_none(ctx):
    assert [c.summary for c in SwapTask().plan(ctx)] == [
        f"create a 4G swap file at {swap.SWAPFILE} and enable it now and at boot"
    ]


def test_existing_swap_of_any_kind_is_left_alone(ctx, monkeypatch):
    monkeypatch.setattr(swap.system, "swaps", lambda: ["/dev/sda2"])
    assert SwapTask().plan(ctx) == []


def test_an_inactive_swap_file_is_enabled_not_recreated(ctx):
    swap.SWAPFILE.write_text("")
    assert [c.summary for c in SwapTask().plan(ctx)] == [
        f"enable the existing {swap.SWAPFILE} now and at boot"
    ]


def test_not_enough_disk_or_btrfs_is_noted_not_attempted(ctx, monkeypatch):
    monkeypatch.setattr(swap, "_free_bytes", lambda: 4 * GIB)
    assert SwapTask().plan(ctx) == []
    assert any("not enough free disk" in n for n in ctx.notes)
    monkeypatch.setattr(swap, "_free_bytes", lambda: 100 * GIB)
    monkeypatch.setattr(swap, "_root_fs", lambda: "btrfs")
    assert SwapTask().plan(ctx) == []
    assert any("btrfs" in n for n in ctx.notes)


def test_disabled_by_config_in_containers_and_on_wsl(ctx, make_ctx, monkeypatch):
    assert SwapTask().enabled(ctx)
    assert not SwapTask().enabled(make_ctx(Config(swap=Swap(enabled=False))))
    assert not SwapTask().enabled(replace(ctx, facts=replace(FACTS, wsl=True)))
    monkeypatch.setattr(swap.system, "in_container", lambda: True)
    assert not SwapTask().enabled(ctx)


def test_swaps_reads_proc_swaps(tmp_path):
    table = tmp_path / "swaps"
    table.write_text("Filename\tType\tSize\tUsed\tPriority\n/swapfile  file  2097148  0  -2\n")
    assert system.swaps(table) == ["/swapfile"]
    table.write_text("Filename\tType\tSize\tUsed\tPriority\n")
    assert system.swaps(table) == []
    assert system.swaps(tmp_path / "missing") == []


def test_fstab_entry_is_added_once(tmp_path):
    fstab = tmp_path / "fstab"
    fstab.write_text("UUID=abc / ext4 defaults 0 1\n")
    line = swap.fstab_line(fstab.read_text())
    assert line == f"{swap.SWAPFILE} none swap sw 0 0\n"
    assert swap.fstab_line(fstab.read_text() + line) is None
