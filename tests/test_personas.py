from __future__ import annotations

import io
import re
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FACTS

from dotkit import cli, onboard
from dotkit.config import App, Config, ConfigError, Docker, Persona, Profile, User, load, resolve
from dotkit.onboard import Hardware

SERVER = Hardware(ram_gb=4, cpus=2, desktop=False, gpu="")

PERSONAS = {
    "node": Persona(
        about="Node.js development",
        docker=True,
        packages=("build-essential",),
        tools={"node": "lts", "pnpm": "latest"},
        apps=("doppler", "agent"),
    ),
    "ai": Persona(about="AI agents", tools={"node": "lts", "rtk": "latest"}, apps=("agent",)),
    "k8s": Persona(about="Kubernetes", modules=("kind",), aliases={"k": "kubectl", "g": "never wins"}),
}
BASE = Config(
    personas=PERSONAS,
    packages=("git",),
    tools={"fzf": "latest"},
    modules=("git",),
    aliases={"g": "git"},
    docker=Docker(enabled=True),
    apps={
        "doppler": App(when=("persona",), apt=("doppler",)),
        "agent": App(when=("persona",), mise={"agent": "latest"}),
        "gui-agent": App(when=("persona", "desktop"), apt=("gui",)),
        "tree": App(apt=("tree",)),
    },
)


def _resolve(*personas: str, config: Config = BASE, **profile) -> Config:
    answers = Profile(role="server", gpu=False, docker=False, heavy=False, personas=personas, **profile)
    return resolve(replace(config, profile=answers), nvidia_gpu=False)


def test_no_persona_means_only_the_base():
    cfg = _resolve()
    assert cfg.tools == {"fzf": "latest"} and cfg.packages == ("git", "tree")
    assert sorted(cfg.apps) == ["tree"]
    assert not cfg.docker.enabled and cfg.modules == ("git",)


def test_a_persona_adds_its_packages_tools_apps_and_docker():
    cfg = _resolve("node")
    assert cfg.packages == ("git", "build-essential", "doppler", "tree")
    assert cfg.tools == {"fzf": "latest", "node": "lts", "pnpm": "latest", "agent": "latest"}
    assert sorted(cfg.apps) == ["agent", "doppler", "tree"]
    assert cfg.docker.enabled  # the persona needs Docker even though the profile declined it


def test_personas_combine_and_share_apps_and_tools():
    cfg = _resolve("node", "ai", "k8s")
    assert cfg.tools["rtk"] == "latest" and cfg.tools["node"] == "lts"
    assert cfg.modules == ("git", "kind")
    assert cfg.aliases == {"k": "kubectl", "g": "git"}  # the top-level alias wins
    assert cfg.enabled_modules[-2:] == ("git", "kind")


def test_config_can_still_veto_docker_for_a_persona():
    config = replace(BASE, docker=Docker(enabled=False))
    assert not _resolve("node", config=config).docker.enabled


def test_persona_apps_still_honour_their_other_conditions():
    config = replace(BASE, personas={**PERSONAS, "ai": replace(PERSONAS["ai"], apps=("gui-agent",))})
    assert "gui-agent" not in _resolve("ai", config=config).apps  # a server: no GUI apps


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "personas: {a: {}}\nprofile: {personas: [nope]}",
            "profile.personas: no such persona 'nope' (available: a)",
        ),
        ("personas: {a: {apps: [x]}}", "personas.a.apps: no such app 'x'"),
        ("apps: {t: {apt: [t]}}\npersonas: {a: {apps: [t]}}", "apps.t.when: add `persona`"),
        ("personas: {A: {}}", "personas: invalid name 'A'"),
        ("personas: {desktop: {}}", "personas: 'desktop' is a `when` condition"),
        ("personas: {a: {tools: {node: lts}}, b: {tools: {node: '22'}}}", "node: personas.b wants '22'"),
        ("tools: {node: '20'}\npersonas: {a: {tools: {node: lts}}}", "node: personas.a wants 'lts'"),
        ("personas: {a: {modules: [nope]}}", "personas.a.modules: no such module 'nope'"),
        ("personas: {a: {aliases: {'bad name': x}}}", "invalid alias name"),
        ("swap: {size: lots}", "swap.size: expected auto or a size such as 4G"),
    ],
)
def test_validation_errors(tmp_path, text, message):
    (tmp_path / "config.yaml").write_text(text)
    (tmp_path / "home" / "git").mkdir(parents=True)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load(tmp_path / "config.yaml", home_dir=tmp_path / "home")


# -- the real config --------------------------------------------------------------------


def test_node_dev_server_from_the_real_config():
    cfg = load(Path("config.yaml"), home_dir=Path("home"))
    server = _resolve("node", config=cfg)
    assert {"node", "pnpm", "wrangler", "supabase"} <= server.tools.keys()
    assert {"doppler", "claude-code"} <= server.apps.keys()
    assert server.docker.enabled
    assert "kubectl" not in server.tools and "kubectl" not in _resolve(config=cfg).tools
    assert not any("desktop" in app.when for app in server.apps.values())


def test_public_config_holds_no_identity():
    # config.yaml is public: name and email are asked on the first run and saved in
    # this machine's profile.yaml (gitignored).
    assert load(Path("config.yaml")).user == User()


# -- onboarding -------------------------------------------------------------------------


def _onboard(answers: str | None, *, config: Config = BASE, given=None, only=None) -> Profile:
    tty = io.StringIO(answers) if answers is not None else None
    return onboard.onboard(config, FACTS, given=given or {}, tty=tty, hw=SERVER, only=only)


def test_personas_are_asked_by_number_or_name(capsys):
    # role, personas, docker (skipped: node needs it), heavy
    profile = _onboard("s\n1, k8s\n\n")
    assert profile.personas == ("node", "k8s") and profile.docker
    out = capsys.readouterr().out
    assert "Node.js development" in out and "Docker is installed: the node persona needs it" in out


def test_bad_persona_is_asked_again_and_none_is_allowed(capsys):
    assert _onboard("s\n9\nnone\nn\n").personas == ()
    assert "Please answer with numbers or names" in capsys.readouterr().out


def test_persona_flag_skips_the_question_and_default_is_none():
    assert _onboard(None, given={"personas": ["ai"]}).personas == ("ai",)
    assert _onboard(None).personas == ()
    with pytest.raises(ConfigError, match="no such persona 'nope'"):
        _onboard(None, given={"personas": ["nope"]})


def test_saved_personas_are_the_default_and_round_trip(tmp_path):
    saved = Profile(role="server", gpu=False, docker=True, heavy=False, personas=("node", "ai"))
    config = replace(BASE, profile=saved)
    assert _onboard("\n\n\n", config=config) == saved
    path = tmp_path / "profile.yaml"
    onboard.save(path, saved, User(name='Ada "Countess" Lovelace', email="ada@example.com"))
    (tmp_path / "config.yaml").write_text("personas: {node: {}, ai: {}}")
    loaded = load(tmp_path / "config.yaml", profile=path)
    assert loaded.profile == saved
    assert loaded.user == User(name='Ada "Countess" Lovelace', email="ada@example.com")


def test_old_profiles_are_asked_only_for_personas(capsys):
    saved = Profile(role="server", gpu=False, docker=False, heavy=False)
    profile = _onboard("2\n", config=replace(BASE, profile=saved), only=frozenset({"personas"}))
    assert profile == replace(saved, personas=("ai",))


# -- identity ---------------------------------------------------------------------------


def test_identity_is_asked_with_the_existing_git_identity_as_default(capsys):
    detected = User(name="Ada Lovelace", email="ada@example.com")
    user = onboard.identity(Config(), io.StringIO("\nnew@example.com\n"), detected)
    assert user == User(name="Ada Lovelace", email="new@example.com")
    assert "stays on this machine" in capsys.readouterr().out


def test_identity_without_a_terminal_keeps_what_is_known():
    detected = User(name="Ada Lovelace", email="ada@example.com")
    assert onboard.identity(Config(), None, detected) == detected
    saved = Config(user=User(name="Saved", email="saved@example.com"))
    assert onboard.identity(saved, None, detected) == saved.user


def test_persona_flag_parses_lists_and_none():
    assert cli._parse(["--persona", "node, k8s"]).personas == ["node", "k8s"]
    assert cli._parse(["--personas", "none"]).personas == []
    assert cli._parse([]).personas is None
