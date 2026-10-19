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
    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: set()))
    assert not Cuda().enabled(make_ctx(Config(nvidia=Nvidia(cuda=False))))
    ctx = make_ctx(Config(nvidia=Nvidia(cuda=True)))
    assert Cuda().enabled(ctx)
    assert [c.summary for c in Cuda().plan(ctx)] == ["install cuda-toolkit (several GB)"]
