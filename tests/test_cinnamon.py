from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import FACTS, write

from dotkit.config import Cinnamon as CinnamonConfig
from dotkit.config import Config, Profile, resolve
from dotkit.tasks import cinnamon
from dotkit.tasks.cinnamon import Cinnamon

MINT = replace(FACTS, distro_id="linuxmint")
DUMP = """[/]
top=1

[org/cinnamon]
favorite-apps=['a.desktop']

[org/cinnamon/theme]
name='Mint-Y'
"""


@pytest.fixture
def ctx(make_ctx, monkeypatch):
    monkeypatch.setattr(cinnamon.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cinnamon, "output", lambda argv: DUMP)
    cfg = CinnamonConfig(enabled=True, applets=("a@x",), themes=("T",), packages=("yaru-theme-icon",))
    ctx = make_ctx(Config(cinnamon=cfg))
    ctx.facts = MINT
    return ctx


def test_only_on_linux_mint_with_cinnamon(ctx, monkeypatch):
    assert Cinnamon().enabled(ctx)
    ctx.facts = FACTS  # Ubuntu
    assert not Cinnamon().enabled(ctx)
    ctx.facts = MINT
    monkeypatch.setattr(cinnamon.shutil, "which", lambda name: None)  # Mint Xfce/MATE
    assert not Cinnamon().enabled(ctx)


def test_servers_never_get_it():
    cfg = Config(cinnamon=CinnamonConfig(enabled=True))
    server = replace(cfg, profile=Profile(role="server"))
    assert not resolve(server, nvidia_gpu=False).cinnamon.enabled
    assert resolve(cfg, nvidia_gpu=False).cinnamon.enabled


def test_plans_spices_settings_and_only_differing_dconf_keys(ctx):
    settings = ctx.repo / "desktop/cinnamon"
    write(
        settings / "dconf.ini",
        "# saved\n[org/cinnamon]\nfavorite-apps=['b.desktop']\n\n[org/cinnamon/theme]\nname='Mint-Y'\n",
    )
    write(settings / "spices/menu@cinnamon.org/0.json", "{}\n")
    assert [c.summary for c in Cinnamon().plan(ctx)] == [
        "install applet a@x",
        "install theme T",
        "apply 1 applet settings file(s) to ~/.config/cinnamon/spices",
        "apply 1 desktop setting(s) (dconf)",
    ]
    assert Cinnamon().packages(ctx) == ["dconf-cli", "yaru-theme-icon"]


def test_nothing_to_do_when_everything_matches(ctx):
    (ctx.home / ".local/share/cinnamon/applets/a@x").mkdir(parents=True)
    (ctx.home / ".themes/T").mkdir(parents=True)
    write(ctx.repo / "desktop/cinnamon/dconf.ini", DUMP)
    write(ctx.repo / "desktop/cinnamon/spices/x/1.json", "{}\n")
    write(ctx.home / ".config/cinnamon/spices/x/1.json", "{}\n")
    assert Cinnamon().plan(ctx) == []


def test_applet_settings_are_copied_and_old_ones_backed_up(ctx):
    write(ctx.repo / "desktop/cinnamon/spices/x/1.json", "new\n")
    live = write(ctx.home / ".config/cinnamon/spices/x/1.json", "old\n")
    cinnamon._copy_spice_settings(ctx, cinnamon._stale_spice_settings(ctx))
    assert live.read_text() == "new\n"
    assert (ctx.backup_dir / ".config/cinnamon/spices/x/1.json").read_text() == "old\n"


def test_fingerprint_follows_saved_files(ctx):
    before = Cinnamon().fingerprint(ctx)
    write(ctx.repo / "desktop/cinnamon/dconf.ini", "[org/x]\na=1\n")
    assert Cinnamon().fingerprint(ctx) != before


def test_spice_zip_must_hold_one_named_folder(tmp_path, monkeypatch):
    import io
    import zipfile

    def zipped(*names):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name in names:
                archive.writestr(name, "x")
        return buf.getvalue()

    monkeypatch.setattr(cinnamon, "fetch", lambda url, timeout: zipped("T/index.theme", "T/gtk-3.0/gtk.css"))
    cinnamon._spice("themes", "T", tmp_path / "themes")
    assert (tmp_path / "themes/T/gtk-3.0/gtk.css").is_file()

    monkeypatch.setattr(cinnamon, "fetch", lambda url, timeout: zipped("T/ok", "../evil"))
    with pytest.raises(OSError, match="unexpected entry"):
        cinnamon._spice("themes", "T", tmp_path / "other")
