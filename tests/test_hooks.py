from __future__ import annotations

from conftest import write

from dotkit.config import Config
from dotkit.hooks import find_blocked
from dotkit.tasks.hooks import MARKER, Hooks


def test_blocked_words_whole_word_case_insensitive(tmp_path):
    f = write(tmp_path / "a.txt", "ok line\nworks at ACME now\nacmecorp is fine\n")
    assert find_blocked([str(f)], ("acme",)) == [f"{f}:2: contains blocked word 'ACME'"]


def test_no_words_means_no_hits(tmp_path):
    f = write(tmp_path / "a.txt", "anything\n")
    assert find_blocked([str(f)], ()) == []


def test_hooks_task_installs_until_hook_present(make_ctx, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    ctx = make_ctx(Config())
    (ctx.repo / ".git" / "hooks").mkdir(parents=True)
    assert Hooks().enabled(ctx)
    assert [c.summary.split(" (")[0] for c in Hooks().plan(ctx)] == [
        "install pre-commit",
        "install the repo's commit checks",
    ]
    write(ctx.home / ".local/bin/pre-commit")  # what pipx installs
    write(ctx.repo / ".git/hooks/pre-commit", f"#!/bin/sh\n# {MARKER}\n")
    assert Hooks().plan(ctx) == []


def test_hooks_task_disabled_without_git_or_by_config(make_ctx):
    ctx = make_ctx(Config())
    assert not Hooks().enabled(ctx)  # no .git
    (ctx.repo / ".git").mkdir()
    assert not Hooks().enabled(make_ctx(Config(pre_commit=False)))
