from __future__ import annotations

from pathlib import Path

from conftest import write

from dotkit.config import Config
from dotkit.hooks import find_blocked
from dotkit.tasks.hooks import HOOK_TYPES, MARKER, Hooks


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
    # A clone from before commit-msg and pre-push existed: still pending.
    assert [c.summary.split(" (")[0] for c in Hooks().plan(ctx)] == ["install the repo's commit checks"]
    for hook in HOOK_TYPES:
        write(ctx.repo / ".git/hooks" / hook, f"#!/bin/sh\n# {MARKER}\n")
    assert Hooks().plan(ctx) == []


def test_hook_types_match_the_pre_commit_config():
    import yaml

    config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text())
    assert tuple(config["default_install_hook_types"]) == HOOK_TYPES
    assert config["default_stages"] == ["pre-commit"]  # only secret checks opt in to other stages
    late = {
        hook.get("alias", hook["id"])
        for repo in config["repos"]
        for hook in repo["hooks"]
        if set(hook.get("stages", [])) & {"commit-msg", "pre-push"}
    }
    assert late == {"gitleaks-message", "gitleaks-push", "blocked-words"}


def test_public_config_does_not_grant_passwordless_sudo():
    from dotkit.config import load

    assert not load(Path("config.yaml")).sudo_nopasswd


def test_hooks_task_disabled_without_git_or_by_config(make_ctx):
    ctx = make_ctx(Config())
    assert not Hooks().enabled(ctx)  # no .git
    (ctx.repo / ".git").mkdir()
    assert not Hooks().enabled(make_ctx(Config(pre_commit=False)))


def test_blocked_words_read_without_validating_the_rest(tmp_path):
    from dotkit.hooks import blocked_words

    base = write(tmp_path / "config.yaml", "blocked_words: [a]\nnot_a_real_key: 1\n")
    local = write(tmp_path / "config.local.yaml", "blocked_words: [acme, '']\nprofile: {role: x}\n")
    assert blocked_words(base, tmp_path / "missing.yaml") == ("a",)
    assert blocked_words(base, local) == ("acme",)
    write(local, "blocked_words: null\n")
    assert blocked_words(base, local) == ()
