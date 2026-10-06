from __future__ import annotations

import pytest
from conftest import write

from dotkit.adopt import AdoptError, adopt


@pytest.fixture
def env(tmp_path):
    home, repo = tmp_path / "home", tmp_path / "repo"
    config = write(repo / "config.yaml", "shells: {default: fish, install: [fish]}\nmodules: [git]\n")
    home.mkdir()

    def run(*paths, module=None):
        return adopt([home / p for p in paths], repo=repo, home=home, config=config, module=module)

    return home, repo, config, run


def test_adopts_directory_links_back_and_enables_module(env):
    home, repo, config, run = env
    write(home / ".config/htop/htoprc", "fields=0\n")
    write(home / ".config/htop/sub/extra", "x\n")
    messages = run(".config/htop")
    for rel in (".config/htop/htoprc", ".config/htop/sub/extra"):
        assert (home / rel).is_symlink()
        assert (home / rel).resolve() == repo / "home/htop" / rel
    assert "modules: [git, htop]" in config.read_text()
    assert messages[-1] == "next: git add home/htop config.yaml && git commit"


def test_single_file_in_config_uses_stem_as_module(env):
    home, repo, _, run = env
    write(home / ".config/starship.toml")
    run(".config/starship.toml")
    assert (repo / "home/starship/.config/starship.toml").is_file()


def test_home_dotfile_needs_explicit_module(env):
    home, repo, _, run = env
    write(home / ".wgetrc")
    with pytest.raises(AdoptError, match="pass --module"):
        run(".wgetrc")
    run(".wgetrc", module="wget")
    assert (repo / "home/wget/.wgetrc").is_file()


def test_shell_modules_are_not_added_to_config(env):
    home, _, config, run = env
    write(home / ".config/fish/functions/hi.fish")
    run(".config/fish/functions/hi.fish", module="fish")
    assert "modules: [git]\n" in config.read_text()


def test_nothing_moves_when_any_destination_exists(env):
    home, repo, _, run = env
    write(home / ".config/htop/a")
    write(home / ".config/htop/b")
    write(repo / "home/htop/.config/htop/b")
    with pytest.raises(AdoptError, match="already in the repo"):
        run(".config/htop")
    assert not (home / ".config/htop/a").is_symlink()


@pytest.mark.parametrize(
    ("setup", "path", "message"),
    [
        (lambda h: None, ".config/missing", "no such file"),
        (lambda h: (h / ".config").mkdir() or (h / ".config/x").symlink_to(h), ".config/x", "is a symlink"),
    ],
)
def test_rejects_bad_paths(env, setup, path, message):
    home, _, _, run = env
    setup(home)
    with pytest.raises(AdoptError, match=message):
        run(path)


def test_outside_home_rejected(env, tmp_path):
    _, repo, config, _ = env
    with pytest.raises(AdoptError, match="only files inside"):
        adopt([tmp_path / "elsewhere"], repo=repo, home=tmp_path / "home", config=config, module="x")


def test_flags_files_that_look_like_secrets(env):
    home, _, _, run = env
    write(home / ".config/gh/hosts.yml", "oauth_token: abc\n")
    messages = run(".config/gh")
    assert any(m.startswith("WARNING") and "hosts.yml" in m for m in messages)
