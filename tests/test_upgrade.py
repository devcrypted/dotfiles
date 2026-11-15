"""`./install.sh upgrade` and `./install.sh reinstall`."""

from __future__ import annotations

import argparse

import pytest
from conftest import apply

from dotkit import cli, reinstall
from dotkit.apt import Apt, has_remote_source
from dotkit.config import App, AptRepo, Config, ConfigError, Deb, Script
from dotkit.tasks import Change, Task, apps, mise
from dotkit.tasks.apps import Apps
from dotkit.tasks.mise import Mise

APPS = {
    "bitwarden": App(deb=Deb(package="bitwarden", url={"amd64": "https://x/bw.deb"})),
    "vscode": App(deb=Deb(package="code", url={"amd64": "https://x/code.deb"})),
    "todoist": App(flatpak="com.todoist.Todoist"),
    "ghostty": App(script=Script(command="ghostty", url="https://x/install.sh", apt="ghostty")),
    "brave": App(apt_repo=AptRepo(key="k", url="u", packages=("brave-browser",))),
    "agent": App(apt=("agent-cli",), mise={"agent": "latest"}),
}
CONFIG = Config(apps=APPS, tools={"node": "lts", "agent": "latest"}, packages=("git", "agent-cli"))


class Upgradable(Task):
    name = "upgrade"  # same name as the real apt task: `upgrade` reruns it
    summary = "test task"
    once = True

    def __init__(self):
        self.log = []

    def plan(self, ctx):
        return [Change("full-upgrade", lambda: self.log.append("plan"))]

    def upgrade(self, ctx):
        return [Change("refresh", lambda: self.log.append("upgrade"))]


def _args(command):
    return argparse.Namespace(command=command, rerun=[])


def test_upgrade_reruns_the_apt_upgrade_and_every_tasks_upgrade_step(make_ctx, capsys):
    ctx, task = make_ctx(), Upgradable()
    cli.Runner(ctx, _args("apply")).run([task])
    cli.Runner(ctx, _args("apply")).run([task])
    assert task.log == ["plan"]  # one-time on a normal run, and no upgrade step
    cli.Runner(ctx, _args("upgrade")).run([task])
    assert task.log == ["plan", "plan", "upgrade"]
    assert "refresh" in capsys.readouterr().out


def test_plan_never_runs_upgrade_steps(make_ctx):
    task = Upgradable()
    cli.Runner(make_ctx(), _args("plan")).run([task])
    assert task.log == []


def test_mise_upgrades_its_tools(make_ctx, monkeypatch):
    monkeypatch.setattr(mise.shutil, "which", lambda name: "/usr/bin/mise")
    assert [c.summary for c in Mise().upgrade(make_ctx(CONFIG))] == [
        "upgrade mise tools to their newest versions"
    ]
    assert Mise().upgrade(make_ctx(Config())) == []


def test_apps_upgrade_flatpaks_and_debs_that_apt_does_not_track(make_ctx, monkeypatch):
    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: set(names)))
    monkeypatch.setattr(Apt, "repo_managed", staticmethod(lambda package: package == "code"))
    assert [c.summary for c in Apps().upgrade(make_ctx(CONFIG))] == [
        "update flatpak apps",
        "reinstall bitwarden from its latest .deb (no apt repo tracks it)",
    ]


def test_a_deb_from_a_vendor_repo_counts_as_apt_managed():
    tracked = """code:
  Installed: 1.99.0
  Candidate: 1.99.0
  Version table:
 *** 1.99.0 500
        500 https://packages.microsoft.com/repos/code stable/main amd64 Packages
        100 /var/lib/dpkg/status
"""
    local = "bitwarden:\n  Installed: 2026.1\n  Version table:\n *** 2026.1 100\n  100 /var/lib/dpkg/status\n"
    assert has_remote_source(tracked) and not has_remote_source(local)


def test_script_app_prefers_the_distro_package_when_the_archive_has_it(make_ctx, monkeypatch):
    monkeypatch.setattr(apps.shutil, "which", lambda name: None)
    monkeypatch.setattr(apps, "output", lambda argv, **_: "")
    ctx = make_ctx(Config(apps={"ghostty": APPS["ghostty"]}))
    monkeypatch.setattr(Apt, "available", staticmethod(lambda package: True))
    assert [c.summary for c in Apps().plan(ctx)] == ["install ghostty (apt ghostty)"]
    monkeypatch.setattr(Apt, "available", staticmethod(lambda package: False))
    assert [c.summary for c in Apps().plan(ctx)] == ["install ghostty (script https://x/install.sh)"]


# -- reinstall --------------------------------------------------------------------------


def test_reinstall_covers_every_source_of_an_app(make_ctx):
    ctx = make_ctx(CONFIG)
    summaries = [
        c.summary for c in reinstall.plan(ctx, ["agent", "brave", "todoist", "bitwarden", "ghostty"])
    ]
    assert summaries == [
        "reinstall agent-cli (apt)",
        "reinstall agent (mise)",
        "reinstall brave-browser (apt)",
        "reinstall todoist (flatpak com.todoist.Todoist)",
        "reinstall bitwarden (.deb)",
        "reinstall ghostty (script https://x/install.sh)",
    ]


def test_reinstall_takes_tools_and_packages_by_name(make_ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(reinstall, "run", lambda argv, **_: calls.append(argv))
    monkeypatch.setattr(
        Apt, "install", lambda self, packages, reinstall=False: calls.append((packages, reinstall))
    )
    changes = reinstall.plan(make_ctx(CONFIG), ["node", "git"])
    assert [c.summary for c in changes] == ["reinstall node (mise)", "reinstall git (apt)"]
    apply(changes)
    assert calls == [["mise", "install", "--force", "--yes", "node"], (["git"], True)]


def test_reinstall_rejects_names_the_config_does_not_install(make_ctx):
    with pytest.raises(ConfigError, match="'nope' is not an app, tool or package"):
        reinstall.plan(make_ctx(CONFIG), ["nope"])
