from __future__ import annotations

import io
import re
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FACTS

from dotkit import onboard
from dotkit.config import CUDA_PATH, App, AptRepo, Config, ConfigError, Docker, Nvidia, Profile, load, resolve
from dotkit.onboard import Hardware

DESKTOP = Hardware(ram_gb=32, cpus=8, desktop=True, gpu="NVIDIA GeForce RTX 3060")
SERVER = Hardware(ram_gb=2, cpus=2, desktop=False, gpu="")

APPS = {
    "everywhere": App(apt=("tree",)),
    "browser": App(when=("desktop",), apt_repo=AptRepo(key="k", url="u", packages=("brave-browser",))),
    "ide": App(when=("desktop", "heavy"), flatpak="org.example.Ide"),
    "cloud": App(when=("heavy",), mise={"azure": "latest"}),
    "monitor": App(when=("gpu",), apt=("nvtop",)),
    "compose-ui": App(when=("docker",), apt=("lazydocker",)),
    "headless": App(when=("server",), apt=("fail2ban",)),
}
BASE = Config(
    apps=APPS,
    packages=("git",),
    fonts=("JetBrainsMono",),
    docker=Docker(enabled=True),
    nvidia=Nvidia(cuda=True),
)


def _resolve(profile: Profile, gpu: bool = True, config: Config = BASE) -> Config:
    return resolve(replace(config, profile=profile), nvidia_gpu=gpu)


def test_desktop_gets_everything_its_profile_allows():
    cfg = _resolve(Profile(role="desktop", gpu=True, docker=True, heavy=True))
    assert sorted(cfg.apps) == ["browser", "cloud", "compose-ui", "everywhere", "ide", "monitor"]
    assert cfg.packages == ("git", "tree", "nvtop", "lazydocker")
    assert list(cfg.apt_repos) == ["browser"]
    assert cfg.tools == {"azure": "latest"}
    assert cfg.docker.enabled and cfg.nvidia.cuda and cfg.fonts
    assert CUDA_PATH in cfg.path


def test_server_drops_gui_apps_fonts_and_whatever_was_declined():
    cfg = _resolve(Profile(role="server", gpu=False, docker=False, heavy=False))
    assert sorted(cfg.apps) == ["everywhere", "headless"]
    assert cfg.fonts == () and cfg.apt_repos == {} and cfg.tools == {}
    assert not cfg.docker.enabled
    assert cfg.nvidia.enabled is False and not cfg.nvidia.cuda
    assert CUDA_PATH not in cfg.path


def test_gpu_apps_need_the_hardware_too():
    cfg = _resolve(Profile(gpu=True), gpu=False)
    assert "monitor" not in cfg.apps and not cfg.nvidia.cuda


def test_config_can_veto_what_the_profile_wants():
    config = replace(BASE, docker=Docker(enabled=False), nvidia=Nvidia(enabled=False, cuda=True))
    cfg = _resolve(Profile(docker=True, gpu=True), config=config)
    assert not cfg.docker.enabled and not cfg.nvidia.cuda
    assert "compose-ui" not in cfg.apps and "monitor" not in cfg.apps


def test_container_toolkit_follows_docker():
    config = replace(BASE, nvidia=Nvidia(container_toolkit=True))
    assert not _resolve(Profile(docker=False), config=config).nvidia.container_toolkit
    assert _resolve(Profile(docker=True), config=config).nvidia.container_toolkit


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("apps: {x: {when: [desktop]}}", "apps.x: give at least one of"),
        ("apps: {x: {when: [laptop], apt: [a]}}", "apps.x.when[0]: expected desktop | server"),
        ("apps: {X: {apt: [a]}}", "apps: invalid name 'X'"),
        ("apps: {x: {deb: {package: p}}}", "apps.x.deb.url: map at least one architecture"),
        ("apps: {x: {flatpak: [a]}}", "apps.x.flatpak: expected a string"),
        ("tools: {azure: latest}\napps: {x: {mise: {azure: latest}}}", "azure is also in tools"),
        ("profile: {role: laptop}", "profile.role: expected desktop | server"),
        ("profile: {gpu: maybe}", "profile.gpu: expected true or false"),
    ],
)
def test_validation_errors(tmp_path, text, message):
    (tmp_path / "config.yaml").write_text(text)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load(tmp_path / "config.yaml")


def test_profile_file_sits_between_config_and_local_overlay(tmp_path):
    (tmp_path / "config.yaml").write_text("upgrade: true")
    profile = tmp_path / "profile.yaml"
    onboard.save(profile, Profile(role="server", gpu=False, docker=False, heavy=False))
    (tmp_path / "config.local.yaml").write_text("profile: {heavy: true}")
    cfg = load(tmp_path / "config.yaml", tmp_path / "config.local.yaml", profile=profile)
    assert cfg.profile == Profile(role="server", gpu=False, docker=False, heavy=True)


def test_full_example_resolves_for_desktop_and_server():
    cfg = load(Path("config.yaml"))
    desktop = _resolve(Profile(), config=cfg)
    server = _resolve(Profile(role="server", heavy=False, docker=False), config=cfg)
    assert {"brave", "vscode", "ghostty", "bitwarden", "whatsie"} <= desktop.apps.keys()
    assert not any("desktop" in app.when for app in server.apps.values())
    assert "kitty" not in desktop.apps


def test_cloud_overlay_keeps_only_what_claude_uses():
    cfg = load(Path("config.yaml"), Path("cloud.yaml"), home_dir=Path("home"))
    assert cfg.profile == Profile(role="server", gpu=False, docker=False, heavy=False)
    cloud = resolve(cfg, nvidia_gpu=False)
    assert cloud.enabled_modules == ("bash", "shell", "kind", "cloud")
    assert cloud.tools.keys() == {
        "node",
        "pnpm",
        "kubectl",
        "kind",
        "helm",
        "terraform",
        "supabase",
        "wrangler",
        "rtk",
    }
    assert not cloud.apps and not cloud.fonts and not cloud.upgrade and not cloud.docker.enabled


# -- onboarding -------------------------------------------------------------------------


def _onboard(answers: str | None, hw: Hardware, *, config: Config = BASE, given=None) -> Profile:
    tty = io.StringIO(answers) if answers is not None else None
    return onboard.onboard(config, FACTS, given=given or {}, tty=tty, hw=hw)


def test_defaults_follow_the_hardware():
    assert _onboard(None, DESKTOP) == Profile(role="desktop", gpu=True, docker=True, heavy=True)
    assert _onboard(None, SERVER) == Profile(role="server", gpu=False, docker=False, heavy=False)


def test_wsl_defaults_to_cli_only():
    wsl = replace(FACTS, wsl=True)
    assert onboard.onboard(BASE, wsl, given={}, tty=None, hw=DESKTOP).role == "server"


def test_answers_override_defaults_and_bad_input_is_asked_again(capsys):
    profile = _onboard("s\nmaybe\nn\ny\n\n", DESKTOP)
    assert profile == Profile(role="server", gpu=False, docker=True, heavy=False)
    out = capsys.readouterr().out
    assert "RTX 3060" in out and "Please answer y or n" in out


def test_no_gpu_question_without_a_gpu(capsys):
    profile = _onboard("d\nn\nn\n", SERVER)
    assert not profile.gpu and not profile.docker and not profile.heavy
    out = capsys.readouterr().out
    assert "No NVIDIA GPU found" in out and "Only 2 GB RAM" in out


def test_flags_skip_their_question():
    profile = _onboard("n\n", DESKTOP, given={"role": "desktop", "gpu": False, "docker": True})
    assert profile == Profile(role="desktop", gpu=False, docker=True, heavy=False)


def test_saved_answers_are_the_defaults_when_asked_again():
    saved = Profile(role="server", gpu=False, docker=False, heavy=False)
    config = replace(BASE, profile=saved)
    assert _onboard("\n\n\n\n", DESKTOP, config=config) == saved
    assert _onboard(None, DESKTOP, config=config, given={"heavy": True}) == replace(saved, heavy=True)


def test_saved_profile_round_trips(tmp_path):
    path = tmp_path / "profile.yaml"
    profile = Profile(role="server", gpu=False, docker=True, heavy=False)
    onboard.save(path, profile)
    (tmp_path / "config.yaml").write_text("")
    assert load(tmp_path / "config.yaml", profile=path).profile == profile
