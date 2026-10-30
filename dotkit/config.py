"""Load ``config.yaml`` (plus an optional local overlay) into typed, immutable objects.

Validation happens entirely up front: an unknown key, a wrong type or an inconsistent
value stops the run with a precise message before anything on the system changes.
"""

from __future__ import annotations

import re
import types
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import yaml

Shell = Literal["fish", "zsh", "bash"]

# Modules under home/ that are enabled implicitly by `shells.install`.
SHELL_MODULES = frozenset({"fish", "zsh", "bash", "shell"})

_ALIAS_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_REPO_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Conditions an app's `when` may list; each one is a profile answer (see Profile).
Condition = Literal["desktop", "server", "heavy", "docker", "gpu"]
HardenLevel = Literal["none", "standard", "aggressive"]  # not "off": YAML reads that as false
HardenSection = Literal[
    "debloat", "telemetry", "services", "firewall", "kernel", "updates", "desktop", "cleanup"
]
CUDA_PATH = "/usr/local/cuda/bin"


class ConfigError(Exception):
    """A problem in the user's configuration."""


@dataclass(frozen=True)
class User:
    name: str = ""
    email: str = ""


@dataclass(frozen=True)
class Shells:
    default: Shell = "bash"
    install: tuple[Shell, ...] = ("bash",)


@dataclass(frozen=True)
class AptRepo:
    key: str
    url: str
    suite: str = "{codename}"
    components: str = "main"
    packages: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaskRule:
    pattern: str
    replace: str = "****"


@dataclass(frozen=True)
class Docker:
    enabled: bool = False


@dataclass(frozen=True)
class Nvidia:
    enabled: bool | Literal["auto"] = "auto"
    flavor: Literal["open", "proprietary"] = "open"
    container_toolkit: bool = False
    cuda: bool = False


@dataclass(frozen=True)
class Profile:
    """Per-machine answers from onboarding, saved in profile.yaml (gitignored)."""

    role: Literal["desktop", "server"] = "desktop"
    gpu: bool = True  # NVIDIA driver + CUDA, only when such a GPU is present
    docker: bool = True
    heavy: bool = True  # apps marked `when: [heavy]`
    harden: HardenLevel = "none"  # scripts/mint/harden.sh; only asked on Linux Mint


@dataclass(frozen=True)
class Deb:
    package: str  # installed package name, used to check whether it is there
    url: dict[str, str] = field(default_factory=dict)  # dpkg arch -> download URL


@dataclass(frozen=True)
class Script:
    command: str  # skip the script when this command is already on PATH
    url: str


@dataclass(frozen=True)
class App:
    """One installable application. Every source given is used, so an app can pair
    an apt package with a flatpak (e.g. podman + Podman Desktop)."""

    when: tuple[Condition, ...] = ()
    apt: tuple[str, ...] = ()
    apt_repo: AptRepo | None = None
    flatpak: str = ""
    deb: Deb | None = None
    script: Script | None = None
    mise: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Cinnamon:
    """Linux Mint Cinnamon look and feel; only used on a desktop running Mint + Cinnamon."""

    enabled: bool = False
    applets: tuple[str, ...] = ()  # Spices applet UUIDs
    themes: tuple[str, ...] = ()  # Spices theme names
    packages: tuple[str, ...] = ()  # icon/cursor themes and applet dependencies


@dataclass(frozen=True)
class Harden:
    """Linux Mint debloat and hardening; the profile's `harden` answer turns it on."""

    skip: tuple[HardenSection, ...] = ()


@dataclass(frozen=True)
class Ssh:
    generate_key: bool = True


@dataclass(frozen=True)
class Config:
    user: User = field(default_factory=User)
    shells: Shells = field(default_factory=Shells)
    prompt: Literal["starship", "builtin"] = "starship"
    modules: tuple[str, ...] = ()
    packages: tuple[str, ...] = ()
    apt_repos: dict[str, AptRepo] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    fonts: tuple[str, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    path: tuple[str, ...] = ()
    mask: tuple[MaskRule, ...] = ()
    upgrade: bool = True
    docker: Docker = field(default_factory=Docker)
    nvidia: Nvidia = field(default_factory=Nvidia)
    ssh: Ssh = field(default_factory=Ssh)
    cinnamon: Cinnamon = field(default_factory=Cinnamon)
    harden: Harden = field(default_factory=Harden)
    sudo_nopasswd: bool = False
    pre_commit: bool = True
    blocked_words: tuple[str, ...] = ()
    apps: dict[str, App] = field(default_factory=dict)
    profile: Profile | None = None

    @property
    def enabled_modules(self) -> tuple[str, ...]:
        """Every home/ module to link: the shells, the shared `shell` module, then `modules`."""
        return (*self.shells.install, "shell", *self.modules)


def load(
    base: Path,
    overlay: Path | None = None,
    *,
    home_dir: Path | None = None,
    profile: Path | None = None,
) -> Config:
    """Read ``base``, deep-merge ``profile`` and then ``overlay`` when they exist, and
    validate the result.

    ``home_dir`` is the repo's ``home/`` directory; when given, module names are
    checked against it.
    """
    data = _read(base)
    sources = [base.name]
    for extra in (profile, overlay):
        if extra is not None and extra.exists():
            data = merge(data, _read(extra))
            sources.append(extra.name)
    try:
        config = _convert(Config, data, "")
        _check(config, home_dir)
    except ConfigError as exc:
        raise ConfigError(f"{' + '.join(sources)}: {exc}") from None
    return config


def resolve(config: Config, *, nvidia_gpu: bool) -> Config:
    """Apply the machine profile: keep only the apps whose `when` holds and fold their
    apt packages, apt repos and mise tools into the matching top-level sections.

    config.yaml says what is allowed on any machine; the profile narrows it, so
    `docker.enabled: false` there still wins over a profile that wants Docker.
    """
    profile = config.profile or Profile()
    gpu = profile.gpu and nvidia_gpu and config.nvidia.enabled is not False
    docker = config.docker.enabled and profile.docker
    holds = {
        "desktop": profile.role == "desktop",
        "server": profile.role == "server",
        "heavy": profile.heavy,
        "docker": docker,
        "gpu": gpu,
    }
    apps = {name: app for name, app in config.apps.items() if all(holds[c] for c in app.when)}
    packages = list(config.packages)
    repos, tools = dict(config.apt_repos), dict(config.tools)
    for name, app in apps.items():
        packages += app.apt
        if app.apt_repo:
            repos[name] = app.apt_repo
        tools.update(app.mise)
    cuda = gpu and config.nvidia.cuda
    return replace(
        config,
        apps=apps,
        packages=tuple(dict.fromkeys(packages)),
        apt_repos=repos,
        tools=tools,
        # Servers are reached over SSH: fonts belong on the client's terminal.
        fonts=config.fonts if holds["desktop"] else (),
        docker=replace(config.docker, enabled=docker),
        cinnamon=replace(config.cinnamon, enabled=config.cinnamon.enabled and holds["desktop"]),
        nvidia=replace(
            config.nvidia,
            enabled=config.nvidia.enabled if profile.gpu else False,
            container_toolkit=config.nvidia.container_toolkit and docker,
            cuda=cuda,
        ),
        path=(*config.path, CUDA_PATH) if cuda and CUDA_PATH not in config.path else config.path,
    )


def merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings. Lists and scalars replace; ``null`` deletes a key."""
    out = dict(base)
    for key, value in overlay.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def _read(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except OSError as exc:
        raise ConfigError(f"{path}: {exc.strerror or exc}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data


def _convert(tp: Any, value: Any, where: str) -> Any:
    """Convert parsed YAML ``value`` into type ``tp``, raising ConfigError on mismatch."""
    origin = get_origin(tp)

    if is_dataclass(tp):
        if not isinstance(value, dict):
            raise _type_error(where, "a mapping", value)
        hints = get_type_hints(tp)
        known = [f.name for f in fields(tp)]
        unknown = sorted(set(value) - set(known))
        if unknown:
            raise ConfigError(
                f"{where or 'top level'}: unknown key {', '.join(map(repr, unknown))} "
                f"(expected: {', '.join(known)})"
            )
        kwargs = {k: _convert(hints[k], v, _join(where, k)) for k, v in value.items()}
        try:
            return tp(**kwargs)
        except TypeError:
            required = [f.name for f in fields(tp) if f.name not in kwargs]
            raise ConfigError(f"{where}: missing required key(s): {', '.join(required)}") from None

    if origin is Literal:
        allowed = get_args(tp)
        # `True in ("auto",)` is False, but guard against bool/int aliasing anyway.
        if any(value == a and type(value) is type(a) for a in allowed):
            return value
        raise _type_error(where, " | ".join(map(str, allowed)), value)

    if origin in (Union, types.UnionType):
        others = [a for a in get_args(tp) if a is not type(None)]
        if value is not None and len(others) == 1:  # `X | None`: report X's own error
            return _convert(others[0], value, where)
        for arg in get_args(tp):
            try:
                return _convert(arg, value, where)
            except ConfigError:
                continue
        raise _type_error(where, " or ".join(_describe(a) for a in get_args(tp)), value)

    if origin is tuple:
        if not isinstance(value, list):
            raise _type_error(where, "a list", value)
        item = get_args(tp)[0]
        return tuple(_convert(item, v, f"{where}[{i}]") for i, v in enumerate(value))

    if origin is dict:
        if not isinstance(value, dict):
            raise _type_error(where, "a mapping", value)
        key_type, value_type = get_args(tp)
        return {
            _convert(key_type, k, where): _convert(value_type, v, _join(where, str(k)))
            for k, v in value.items()
        }

    if tp is type(None):
        if value is None:
            return None
        raise _type_error(where, "null", value)

    if tp is bool:
        if isinstance(value, bool):
            return value
        raise _type_error(where, "true or false", value)

    if tp is str:
        if isinstance(value, str):
            return value
        hint = ' (quote it, e.g. "3.12")' if isinstance(value, (int, float)) else ""
        raise _type_error(where, "a string" + hint, value)

    raise TypeError(f"unsupported config type {tp!r}")  # programming error, not user error


def _check(config: Config, home_dir: Path | None) -> None:
    """Cross-field rules that the type system can't express."""
    shells = config.shells
    if not shells.install:
        raise ConfigError("shells.install: list at least one shell")
    if shells.default not in shells.install:
        raise ConfigError(f"shells.default: {shells.default!r} must also be in shells.install")

    for module in config.modules:
        if module in SHELL_MODULES:
            raise ConfigError(f"modules: {module!r} is enabled automatically by shells.install; remove it")
        if home_dir is not None and not (home_dir / module).is_dir():
            available = sorted(
                p.name for p in home_dir.iterdir() if p.is_dir() and p.name not in SHELL_MODULES
            )
            raise ConfigError(f"modules: no such module {module!r} (available: {', '.join(available)})")

    for name in config.aliases:
        if not _ALIAS_NAME.match(name):
            raise ConfigError(f"aliases: invalid alias name {name!r}")
    for name in config.env:
        if not _ENV_NAME.match(name):
            raise ConfigError(f"env: invalid variable name {name!r}")
    for name, repo in config.apt_repos.items():
        if not _REPO_NAME.match(name):
            raise ConfigError(f"apt_repos: invalid name {name!r} (use a-z, 0-9 and -)")
        if not repo.packages:
            raise ConfigError(f"apt_repos.{name}.packages: list at least one package")

    for name, app in config.apps.items():
        where = f"apps.{name}"
        if not _REPO_NAME.match(name):
            raise ConfigError(f"apps: invalid name {name!r} (use a-z, 0-9 and -)")
        if not (app.apt or app.apt_repo or app.flatpak or app.deb or app.script or app.mise):
            raise ConfigError(f"{where}: give at least one of apt, apt_repo, flatpak, deb, script, mise")
        if app.apt_repo and not app.apt_repo.packages:
            raise ConfigError(f"{where}.apt_repo.packages: list at least one package")
        if app.apt_repo and name in config.apt_repos:
            raise ConfigError(f"{where}: apt_repos.{name} already exists; rename one of them")
        if app.deb and not app.deb.url:
            raise ConfigError(f"{where}.deb.url: map at least one architecture to a URL")
        clash = sorted(app.mise.keys() & config.tools.keys())
        if clash:
            raise ConfigError(f"{where}.mise: {', '.join(clash)} is also in tools; keep one")


def _join(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def _describe(tp: Any) -> str:
    if get_origin(tp) is Literal:
        return " | ".join(map(str, get_args(tp)))
    return {bool: "true or false", str: "a string"}.get(tp, getattr(tp, "__name__", str(tp)))


def _type_error(where: str, expected: str, value: Any) -> ConfigError:
    return ConfigError(f"{where or 'top level'}: expected {expected}, got {value!r}")
