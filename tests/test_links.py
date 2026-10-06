from __future__ import annotations

import os

import pytest
from conftest import apply, write

from dotkit.config import Config, ConfigError, Shells
from dotkit.tasks.links import Links


def _cfg(*modules):
    return Config(shells=Shells(default="bash", install=("bash",)), modules=modules)


def test_links_new_files_and_is_idempotent(make_ctx):
    ctx = make_ctx(_cfg("git"))
    src = write(ctx.repo / "home/git/.config/git/config")
    apply(Links().plan(ctx))
    target = ctx.home / ".config/git/config"
    assert target.is_symlink() and target.resolve() == src
    assert Links().plan(ctx) == []


def test_existing_file_is_backed_up_with_mirrored_path(make_ctx):
    ctx = make_ctx(_cfg("git"))
    write(ctx.repo / "home/git/.config/git/config", "new\n")
    write(ctx.home / ".config/git/config", "old\n")
    changes = Links().plan(ctx)
    assert "backed up" in changes[0].summary
    apply(changes)
    assert (ctx.backup_dir / ".config/git/config").read_text() == "old\n"
    assert (ctx.home / ".config/git/config").read_text() == "new\n"


def test_wrong_and_broken_symlinks_are_replaced(make_ctx, tmp_path):
    ctx = make_ctx(_cfg("tmux"))
    write(ctx.repo / "home/tmux/.config/tmux/tmux.conf")
    target = ctx.home / ".config/tmux/tmux.conf"
    target.parent.mkdir(parents=True)
    target.symlink_to(tmp_path / "does-not-exist")
    apply(Links().plan(ctx))
    assert target.resolve() == ctx.repo / "home/tmux/.config/tmux/tmux.conf"
    assert (ctx.backup_dir / ".config/tmux/tmux.conf").is_symlink()


def test_symlinked_parent_dir_is_backed_up_not_written_through(make_ctx, tmp_path):
    ctx = make_ctx(_cfg("fish"))
    write(ctx.repo / "home/fish/.config/fish/conf.d/a.fish")
    elsewhere = tmp_path / "elsewhere"
    write(elsewhere / "conf.d/a.fish", "keep me\n")
    (ctx.home / ".config").mkdir()
    (ctx.home / ".config/fish").symlink_to(elsewhere)
    apply(Links().plan(ctx))
    assert not (ctx.home / ".config/fish").is_symlink()
    assert (elsewhere / "conf.d/a.fish").read_text() == "keep me\n"  # untouched


def test_prunes_links_from_disabled_modules_and_stow(make_ctx):
    ctx = make_ctx(_cfg("git", "tmux"))
    write(ctx.repo / "home/git/.config/git/config")
    write(ctx.repo / "home/tmux/.config/tmux/tmux.conf")
    apply(Links().plan(ctx))
    Links().commit(ctx)
    (ctx.home / ".zshrc").symlink_to(write(ctx.repo / ".zshrc"))  # left over by stow
    (ctx.home / "notes").symlink_to(ctx.home)  # unrelated link: must survive

    ctx2 = make_ctx(_cfg("git"))
    ctx2.state = ctx.state
    changes = Links().plan(ctx2)
    assert sorted(c.summary.split()[1] for c in changes) == ["~/.config/tmux/tmux.conf", "~/.zshrc"]
    apply(changes)
    assert not (ctx.home / ".config/tmux/tmux.conf").exists()
    assert (ctx.home / "notes").is_symlink()


def test_repo_symlinked_into_home_is_never_pruned(make_ctx):
    ctx = make_ctx(_cfg())
    (ctx.home / "dotfiles").symlink_to(ctx.repo)
    assert Links().plan(ctx) == []


def test_duplicate_targets_across_modules_fail(make_ctx):
    ctx = make_ctx(_cfg("git", "tmux"))
    write(ctx.repo / "home/git/.same")
    write(ctx.repo / "home/tmux/.same")
    with pytest.raises(ConfigError, match="provided by both modules 'git' and 'tmux'"):
        Links().plan(ctx)


def test_plan_does_not_touch_the_filesystem(make_ctx):
    ctx = make_ctx(_cfg("git"))
    write(ctx.repo / "home/git/.config/git/config")
    write(ctx.home / ".config/git/config", "old\n")
    before = sorted(os.walk(ctx.home))
    Links().plan(ctx)
    assert sorted(os.walk(ctx.home)) == before
