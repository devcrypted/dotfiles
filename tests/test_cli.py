from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from dotkit import cli
from dotkit.config import ConfigError
from dotkit.tasks import TASKS, Change, Task


class Counter(Task):
    name = "counter"
    summary = "test task"
    once = True

    def __init__(self, setting):
        self.setting = setting
        self.applied = 0

    def fingerprint(self, ctx):
        return self.setting

    def plan(self, ctx):
        return [Change("do it", self._apply)]

    def _apply(self):
        self.applied += 1


def _args(command="apply", rerun=()):
    return argparse.Namespace(command=command, rerun=list(rerun))


def test_once_task_runs_once_then_again_when_fingerprint_changes(make_ctx, capsys):
    ctx = make_ctx()
    task = Counter("a")
    cli.Runner(ctx, _args()).run([task])
    cli.Runner(ctx, _args()).run([task])
    assert task.applied == 1
    assert "done" in capsys.readouterr().out

    task.setting = "b"
    cli.Runner(ctx, _args()).run([task])
    assert task.applied == 2

    cli.Runner(ctx, _args(rerun=["counter"])).run([task])
    assert task.applied == 3


def test_plan_never_applies(make_ctx, capsys):
    task = Counter("a")
    cli.Runner(make_ctx(), _args("plan")).run([task])
    assert task.applied == 0
    assert "Plan: 1 to change" in capsys.readouterr().out


def test_failure_returns_nonzero_and_shows_output(make_ctx, capsys):
    from dotkit.system import CommandError

    class Boom(Counter):
        def _apply(self):
            raise CommandError(["x"], 3, "line1\nreason")

    assert cli.Runner(make_ctx(), _args()).run([Boom("a")]) == 1
    out = capsys.readouterr().out
    assert "`x` exited with 3" in out and "reason" in out


def _select(**kw):
    defaults = {"only": [], "skip": [], "rerun": [], "no_once": False, "once_only": False}
    return [t.name for t in cli._select(argparse.Namespace(**{**defaults, **kw}))]


def test_task_selection():
    assert _select(only=["links", "git"]) == ["links", "git"]
    assert "nvidia" not in _select(no_once=True)
    assert "nvidia" in _select(no_once=True, rerun=["nvidia"])
    assert all(t in ("upgrade", "nvidia", "ssh") for t in _select(once_only=True))
    with pytest.raises(ConfigError, match="unknown task 'nope'"):
        _select(skip=["nope"])


def test_every_task_is_documented_in_features():
    features = Path("FEATURES.md").read_text()
    documented = set(re.findall(r"^\| `([a-z]+)`", features, re.M))
    assert documented == {t.name for t in TASKS}
