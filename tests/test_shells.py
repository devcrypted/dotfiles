from __future__ import annotations

from conftest import apply, write

from dotkit.config import Config, Shells
from dotkit.fsops import BLOCK_START
from dotkit.tasks import shells
from dotkit.tasks.shells import _rc_change


def _ctx(make_ctx):
    return make_ctx(Config(shells=Shells(default="zsh", install=("zsh", "fish"))))


def test_rc_block_added_and_idempotent(make_ctx):
    ctx = _ctx(make_ctx)
    write(ctx.home / ".zshrc", "# tool line\n")
    apply([_rc_change(ctx, "zsh")])
    text = (ctx.home / ".zshrc").read_text()
    assert text.startswith("# tool line\n") and BLOCK_START in text
    assert '. "$HOME/.config/zsh/init.zsh"' in text
    assert _rc_change(ctx, "zsh") is None


def test_symlinked_rc_replaced_by_local_file(make_ctx):
    ctx = _ctx(make_ctx)
    target = write(ctx.repo / ".zshrc", "old repo rc\n")
    (ctx.home / ".zshrc").symlink_to(target)
    apply([_rc_change(ctx, "zsh")])
    assert not (ctx.home / ".zshrc").is_symlink()
    assert target.read_text() == "old repo rc\n"  # repo file untouched
    assert (ctx.backup_dir / ".zshrc").is_symlink()


def test_fish_needs_no_rc_change(make_ctx):
    assert _rc_change(_ctx(make_ctx), "fish") is None


def test_zsh_plugins_requested_only_with_zsh(make_ctx):
    assert "zsh-autosuggestions" in shells.Shells().packages(_ctx(make_ctx))
    bash_only = make_ctx(Config())
    assert shells.Shells().packages(bash_only) == ["bash"]
