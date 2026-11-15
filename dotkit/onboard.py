"""First-run onboarding: a few questions about this machine, saved to profile.yaml.

The answers decide which `apps` in config.yaml apply here (see `config.resolve`).
Hardware is detected first, so the defaults are usually right, and a question that
can't apply (CUDA without an NVIDIA GPU) is not asked at all.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from . import system
from .config import Config, ConfigError, Profile, User
from .system import Facts

HEADER = """\
# This machine's answers to ./install.sh onboarding. Gitignored: each machine has its own,
# and it is the only place your name and email are kept (config.yaml is public).
# Edit and rerun, or run `./install.sh setup` to answer the questions again.
"""
COMMENTS = {
    "role": "desktop | server (server: CLI only, no GUI apps or fonts)",
    "gpu": "NVIDIA driver + CUDA (only used when an NVIDIA GPU is present)",
    "docker": "Docker Engine",
    "heavy": "apps marked `when: [heavy]` in config.yaml",
    "harden": "none | standard | aggressive: scripts/mint/harden.sh (Linux Mint only)",
    "cinnamon": "apply the saved Cinnamon desktop look in desktop/cinnamon/",
    "personas": "toolsets from `personas` in config.yaml",
}
MINT = "linuxmint"


@dataclass(frozen=True)
class Hardware:
    ram_gb: int
    cpus: int
    desktop: bool  # a graphical session or display manager exists
    gpu: str  # NVIDIA GPU name, "" when there is none
    cinnamon: bool = False  # the Cinnamon desktop is installed

    @classmethod
    def probe(cls, facts: Facts) -> Hardware:
        return cls(
            ram_gb=system.ram_gb(),
            cpus=os.cpu_count() or 0,
            desktop=system.has_desktop(),
            gpu=system.gpu_name() if facts.nvidia_gpu else "",
            cinnamon=shutil.which("cinnamon") is not None,
        )

    def describe(self, facts: Facts) -> str:
        return " · ".join(
            (
                facts.pretty,
                f"{self.ram_gb} GB RAM",
                f"{self.cpus} CPUs",
                self.gpu or "no NVIDIA GPU",
                "desktop session" if self.desktop else "no desktop session",
            )
        )


def defaults(facts: Facts, hw: Hardware, role: str | None = None) -> Profile:
    """What a machine like this most likely wants. WSL counts as CLI-only."""
    role = role or ("desktop" if hw.desktop and not facts.wsl else "server")
    desktop = role == "desktop"
    return Profile(
        role=role,  # type: ignore[arg-type]
        gpu=bool(hw.gpu),
        docker=desktop and hw.ram_gb >= 4,
        heavy=desktop and hw.ram_gb >= 8,
        harden="standard" if facts.distro_id == MINT and not facts.wsl else "none",
        cinnamon=desktop and _mint_cinnamon(facts, hw),
    )


def _mint_cinnamon(facts: Facts, hw: Hardware) -> bool:
    return facts.distro_id == MINT and not facts.wsl and hw.cinnamon


def onboard(
    config: Config,
    facts: Facts,
    *,
    given: dict[str, object],
    tty: TextIO | None,
    hw: Hardware | None = None,
    only: frozenset[str] | None = None,
) -> Profile:
    """Build this machine's profile.

    Precedence per answer: ``given`` (command line flags), then the user's reply when
    ``tty`` is set, then the saved profile, then detected defaults. With a saved
    profile, the questions are asked with its answers as the defaults.

    ``only`` limits the questions to these answers, which the saved profile lacks
    (it was written before they existed); the rest are kept as saved.
    """
    hw = hw or Hardware.probe(facts)
    saved = config.profile
    asker = _Asker(tty) if tty else None
    if asker:
        if only:
            print("\nThis machine's profile is missing newer questions.")
        else:
            print("\nUpdating this machine's profile." if saved else "\nThis machine has no profile yet.")
        print(f"Detected: {hw.describe(facts)}")
        print("Answers are saved to profile.yaml. Enter keeps the [default].\n")

    def asking(key: str) -> _Asker | None:
        return asker if only is None or key in only else None

    def default(key: str, detected: object) -> object:
        return getattr(saved, key) if saved and not (only and key in only) else detected

    if "role" in given:
        role = str(given["role"])
    else:
        role = default("role", defaults(facts, hw).role)
        if ask := asking("role"):
            role = ask.choice(
                "Desktop or server? A server gets CLI tools only (no GUI apps, no fonts).",
                {"d": "desktop", "s": "server"},
                role,
            )
    base = defaults(facts, hw, str(role))

    if "personas" in given:
        personas = tuple(given["personas"])  # type: ignore[arg-type]
    else:
        personas = default("personas", base.personas)
        if (ask := asking("personas")) and config.personas:
            personas = ask.multi(
                "Personas: toolsets for the work this machine does. Pick any number.",
                {name: persona.about for name, persona in config.personas.items()},
                personas,
            )
    for name in personas:
        if name not in config.personas:
            available = ", ".join(config.personas) or "none defined"
            raise ConfigError(f"--persona: no such persona {name!r} (available: {available})")
    needs_docker = [name for name in personas if config.personas[name].docker]

    if not hw.gpu:
        gpu = False
        if asking("gpu"):
            print("  - No NVIDIA GPU found: the driver and CUDA are skipped.")
    elif "gpu" in given:
        gpu = given["gpu"]
    else:
        gpu = default("gpu", base.gpu)
        if ask := asking("gpu"):
            gpu = ask.yes(f"Install the NVIDIA driver and CUDA for the {hw.gpu}?", gpu)

    if "docker" in given:
        docker = given["docker"]
    elif needs_docker:
        docker = True
        if asking("docker") or asking("personas"):
            print(f"  - Docker is installed: the {needs_docker[0]} persona needs it.")
    else:
        docker = default("docker", base.docker)
        if ask := asking("docker"):
            docker = ask.yes("Install Docker?", docker)

    heavy_apps = [
        name
        for name, app in config.apps.items()
        if "heavy" in app.when and ("desktop" not in app.when or role == "desktop")
    ]
    if "heavy" in given:
        heavy = given["heavy"]
    else:
        heavy = default("heavy", base.heavy)
        if (ask := asking("heavy")) and heavy_apps:
            low_ram = f" Only {hw.ram_gb} GB RAM here." if hw.ram_gb < 8 else ""
            heavy = ask.yes(f"Install heavy apps ({', '.join(heavy_apps)})?{low_ram}", heavy)

    if facts.distro_id != MINT or facts.wsl:
        harden = "none"  # harden.sh knows Mint's packages and services only
    elif "harden" in given:
        harden = str(given["harden"])
    else:
        harden = default("harden", base.harden)
        if ask := asking("harden"):
            harden = ask.choice(
                "Debloat and harden Linux Mint? Standard removes unused preinstalled apps and "
                "crash reporters, turns on the firewall and kernel hardening; aggressive also "
                "removes LibreOffice, Firefox and more (details: scripts/mint/harden.sh --help).",
                {"s": "standard", "a": "aggressive", "n": "none"},
                harden,
            )

    if role != "desktop" or not _mint_cinnamon(facts, hw):
        cinnamon = False  # the saved look only fits a Linux Mint Cinnamon desktop
    elif "cinnamon" in given:
        cinnamon = given["cinnamon"]
    else:
        cinnamon = default("cinnamon", base.cinnamon)
        if ask := asking("cinnamon"):
            cinnamon = ask.yes(
                "Apply the saved Cinnamon desktop (panel and applets, themes, icons, shortcuts, "
                "gestures from desktop/cinnamon/)? It replaces this desktop's current look.",
                cinnamon,
            )
    if asker:
        print()

    return Profile(
        role=role,  # type: ignore[arg-type]
        gpu=bool(gpu),
        docker=bool(docker),
        heavy=bool(heavy),
        harden=harden,  # type: ignore[arg-type]
        cinnamon=bool(cinnamon),
        personas=tuple(personas),
    )


def identity(config: Config, tty: TextIO | None, detected: User) -> User:
    """Name and email for git commits: the saved ones, else what git already uses here,
    confirmed or replaced by the user when ``tty`` is set."""
    known = User(name=config.user.name or detected.name, email=config.user.email or detected.email)
    if tty is None:
        return known
    print("Git identity for commits. It stays on this machine (profile.yaml); Enter keeps the [default].\n")
    ask = _Asker(tty)
    name = ask.text("Name", known.name)
    email = ask.text("Email", known.email)
    print()
    return User(name=name, email=email)


def git_identity() -> User:
    """The identity git already uses on this machine, if any."""

    def get(key: str) -> str:
        return system.output(["git", "config", "--global", "--get", key]).strip()

    return User(name=get("user.name"), email=get("user.email"))


def save(path: Path, profile: Profile, user: User | None = None) -> None:
    lines = [HEADER]
    if user and (user.name or user.email):
        # JSON strings are valid YAML, whatever characters a name contains.
        lines += [
            "user:\n",
            *(f"  {k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in asdict(user).items()),
        ]
    lines.append("profile:\n")
    for key, value in asdict(profile).items():
        if isinstance(value, bool):
            text = str(value).lower()
        elif isinstance(value, tuple):
            text = f"[{', '.join(value)}]"
        else:
            text = value
        lines.append(f"  {f'{key}: {text}':<16} # {COMMENTS[key]}\n")
    path.write_text("".join(lines))


def terminal() -> TextIO | None:
    """stdin when it's a terminal, /dev/tty when piped (`curl … | bash`), else None."""
    if sys.stdin.isatty():
        return sys.stdin
    try:
        return open("/dev/tty")  # stays open for the rest of the run
    except OSError:
        return None


class _Asker:
    def __init__(self, tty: TextIO) -> None:
        self.tty = tty
        self.number = 0

    def _ask(self, question: str, hint: str, parse) -> object:
        self.number += 1
        while True:
            print(f"  {self.number}. {question} {hint} ", end="", flush=True)
            line = self.tty.readline()
            if not line:  # EOF: keep the default
                print()
                line = "\n"
            answer = parse(line.strip().lower())
            if answer is not None:
                return answer

    def yes(self, question: str, default: object) -> bool:
        def parse(answer: str) -> bool | None:
            if answer == "":
                return bool(default)
            if answer in ("y", "yes", "n", "no"):
                return answer.startswith("y")
            print("     Please answer y or n.")
            return None

        return bool(self._ask(question, "[Y/n]" if default else "[y/N]", parse))

    def choice(self, question: str, options: dict[str, str], default: object) -> str:
        def parse(answer: str) -> str | None:
            if answer == "":
                return str(default)
            for key, value in options.items():
                if answer in (key, value):
                    return value
            print(f"     Please answer {' or '.join(options)}.")
            return None

        hint = "[" + "/".join(k.upper() if v == default else k for k, v in options.items()) + "]"
        return str(self._ask(question, hint, parse))

    def text(self, question: str, default: str) -> str:
        return str(
            self._ask(question, f"[{default}]" if default else "[none]", lambda answer: answer or default)
        )

    def multi(self, question: str, options: dict[str, str], default: object) -> tuple[str, ...]:
        """Any number of ``options`` (name -> description), by number or by name."""
        names = list(options)
        width = max(map(len, names))
        menu = "".join(f"\n       {i}  {name:<{width}}  {options[name]}" for i, name in enumerate(names, 1))

        def parse(answer: str) -> tuple[str, ...] | None:
            if answer == "":
                return tuple(default)  # type: ignore[arg-type]
            if answer in ("none", "-", "0"):
                return ()
            picked = []
            for token in answer.replace(",", " ").split():
                if token.isdigit() and 1 <= int(token) <= len(names):
                    token = names[int(token) - 1]
                if token not in options:
                    print("     Please answer with numbers or names from the list, or `none`.")
                    return None
                picked.append(token)
            return tuple(dict.fromkeys(picked))

        shown = ",".join(default) or "none"  # type: ignore[arg-type]
        return self._ask(
            f"{question}{menu}\n     Numbers or names, e.g. `1 3`, or `none`", f"[{shown}]", parse
        )  # type: ignore[return-value]
