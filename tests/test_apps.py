from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import FACTS, apply

from dotkit.apt import Apt
from dotkit.config import App, Config, Deb, Nvidia, Script
from dotkit.system import CommandError
from dotkit.tasks import apps, cuda
from dotkit.tasks.apps import Apps
from dotkit.tasks.cuda import Cuda

APPS = {
    "bitwarden": App(flatpak="com.bitwarden.desktop"),
    "vscode": App(deb=Deb(package="code", url={"amd64": "https://x/code.deb"})),
    "ghostty": App(script=Script(command="ghostty", url="https://x/install.sh")),
    "tree": App(apt=("tree",)),
}


@pytest.fixture
def ctx(make_ctx, monkeypatch):
    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: set()))
    monkeypatch.setattr(apps.shutil, "which", lambda name: None)
    return make_ctx(Config(apps=APPS))


def _flatpak(monkeypatch, remotes="", installed=""):
    def fake(argv, **_):
        return remotes if argv[1] == "remotes" else installed

    monkeypatch.setattr(apps, "output", fake)


def test_fresh_machine_plans_every_source(ctx, monkeypatch):
    _flatpak(monkeypatch)
    assert [c.summary for c in Apps().plan(ctx)] == [
        "add the Flathub remote",
        "install bitwarden (flatpak com.bitwarden.desktop)",
        "install vscode (.deb)",
        "install ghostty (script https://x/install.sh)",
    ]
    assert Apps().packages(ctx) == ["flatpak"]


def test_nothing_to_do_when_installed(ctx, monkeypatch):
    _flatpak(monkeypatch, remotes="flathub\n", installed="com.bitwarden.desktop\n")
    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: set(names)))
    monkeypatch.setattr(apps.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert Apps().plan(ctx) == []


def test_apt_only_apps_leave_the_task_disabled(make_ctx):
    assert not Apps().enabled(make_ctx(Config(apps={"tree": APPS["tree"]})))


def test_missing_architecture_is_noted_not_failed(ctx, monkeypatch):
    _flatpak(monkeypatch, remotes="flathub", installed="com.bitwarden.desktop")
    ctx = replace(ctx, facts=replace(FACTS, arch="arm64"))
    summaries = [c.summary for c in Apps().plan(ctx)]
    assert "install vscode (.deb)" not in summaries
    assert any("no .deb for arm64" in n for n in ctx.notes)


def test_one_failing_app_does_not_stop_the_run(ctx, monkeypatch, capsys):
    _flatpak(monkeypatch, remotes="flathub", installed="com.bitwarden.desktop")

    def boom(*args, **kwargs):
        raise CommandError(["bash", "-s"], 1, "not compatible")

    monkeypatch.setattr(apps, "_run_script", boom)
    monkeypatch.setattr(apps, "_install_deb", lambda *a: None)
    apply(Apps().plan(ctx))
    assert any(n.startswith("ghostty was not installed") for n in ctx.notes)


@pytest.mark.parametrize(
    ("facts", "repo"),
    [
        ({}, "ubuntu2404/x86_64"),
        ({"distro_id": "linuxmint"}, "ubuntu2404/x86_64"),
        ({"codename": "jammy", "arch": "arm64"}, "ubuntu2204/sbsa"),
        ({"wsl": True}, "wsl-ubuntu/x86_64"),
        ({"distro": "debian", "codename": "bookworm", "version": "12"}, "debian12/x86_64"),
    ],
)
def test_cuda_repo_per_release(make_ctx, facts, repo):
    ctx = replace(make_ctx(), facts=replace(FACTS, **facts))
    assert cuda.repo_url(ctx).endswith(f"/repos/{repo}")


def test_cuda_repo_unknown_release_fails_clearly(make_ctx):
    ctx = replace(make_ctx(), facts=replace(FACTS, codename="focal"))
    with pytest.raises(CommandError):
        cuda.repo_url(ctx)


def test_cuda_task_follows_resolved_config(make_ctx, monkeypatch):
    monkeypatch.setattr(cuda, "interrupted", lambda: [])
    monkeypatch.setattr(cuda, "nvcc_version", lambda: "")
    assert not Cuda().enabled(make_ctx(Config(nvidia=Nvidia(cuda=False))))
    ctx = make_ctx(Config(nvidia=Nvidia(cuda=True)))
    assert Cuda().enabled(ctx)
    assert [c.summary for c in Cuda().plan(ctx)] == ["install cuda-toolkit (several GB)"]


def test_any_working_nvcc_means_cuda_is_installed(make_ctx, monkeypatch):
    monkeypatch.setattr(cuda, "interrupted", lambda: [])
    monkeypatch.setattr(cuda, "nvcc_version", lambda: "12.4")  # e.g. cuda-toolkit-12-4 or the runfile
    assert Cuda().plan(make_ctx(Config(nvidia=Nvidia(cuda=True)))) == []


def test_an_interrupted_install_is_finished_not_redownloaded(make_ctx, monkeypatch):
    monkeypatch.setattr(cuda, "interrupted", lambda: ["cuda-toolkit-13-4", "cuda-nvcc-13-4"])
    monkeypatch.setattr(cuda, "nvcc_version", lambda: "")
    [change] = Cuda().plan(make_ctx(Config(nvidia=Nvidia(cuda=True))))
    assert change.summary == "finish the interrupted CUDA install (2 package(s); no new downloads)"


def test_interrupted_reads_dpkg_states(monkeypatch):
    dpkg = (
        "ii  cuda-cudart-13-4\niU  cuda-nvcc-13-4\niF  cuda-toolkit-13-4\niHR cuda-libs-13-4\nrc  cuda-old\n"
    )
    monkeypatch.setattr(cuda, "output", lambda argv, any_exit=False: dpkg)
    assert cuda.interrupted() == ["cuda-nvcc-13-4", "cuda-toolkit-13-4", "cuda-libs-13-4"]


def test_nvcc_version_needs_an_nvcc_that_runs(monkeypatch, tmp_path):
    nvcc = tmp_path / "nvcc"
    nvcc.write_text("#!/bin/sh\n")
    nvcc.chmod(0o755)
    monkeypatch.setattr(cuda.shutil, "which", lambda name: str(nvcc))
    monkeypatch.setattr(cuda.Path, "glob", lambda self, pattern: iter(()))
    monkeypatch.setattr(cuda, "output", lambda argv: "Cuda compilation tools, release 13.4, V13.4.92\n")
    assert cuda.nvcc_version() == "13.4"
    monkeypatch.setattr(cuda, "output", lambda argv: "")  # broken binary
    assert cuda.nvcc_version() == ""


@pytest.mark.parametrize(
    ("loaded", "flavor", "expected"),
    [
        ("NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  595.99.02", "open", True),
        ("NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  595.99.02", "proprietary", False),
        ("NVRM version: NVIDIA UNIX x86_64 Kernel Module  595.99.02", "proprietary", True),
    ],
)
def test_a_running_driver_counts_as_installed(make_ctx, tmp_path, monkeypatch, loaded, flavor, expected):
    from dotkit.tasks import nvidia

    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: set()))
    version = tmp_path / "version"
    version.write_text(loaded + "\n")
    assert nvidia._driver_installed(make_ctx(), flavor, version) is expected
    assert nvidia._driver_installed(make_ctx(), flavor, tmp_path / "absent") is False
