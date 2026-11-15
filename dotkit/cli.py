"""Command line entry point: ``apply`` (default), ``plan``, ``status``, ``upgrade``, ``reinstall``,
``setup``, ``cloud`` and ``adopt``."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import fields, replace
from datetime import datetime
from pathlib import Path

import yaml

from . import catalog, onboard, reinstall, system
from .adopt import AdoptError, adopt
from .apt import Apt
from .config import Config, ConfigError, Profile, load, resolve
from .state import State, fingerprint
from .system import CommandError, Facts, UnsupportedSystem, detect, sudo
from .tasks import TASKS, Context, Task

REPO = Path(__file__).resolve().parent.parent
# Commands that ask the profile questions when this machine hasn't answered them yet.
_ONBOARDING = ("apply", "plan", "upgrade")


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    system.verbose = args.verbose
    if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        _error("run as your normal user, not with sudo; it asks for a password when needed")
        return 2
    if args.command == "adopt":
        return _adopt(args)
    if args.command == "catalog":
        try:
            print(catalog.dump(REPO), end="")
        except ConfigError as exc:
            _error(str(exc))
            return 2
        return 0
    if args.names and args.command != "reinstall":
        _error(f"unexpected arguments: {' '.join(args.names)} (only `adopt` and `reinstall` take any)")
        return 2
    if args.command == "cloud":
        try:
            _use_cloud_overlay(_config_path(args))
        except ConfigError as exc:
            _error(str(exc))
            return 2
        args.command = "apply"
    try:
        ctx = _context(args)
        tasks = _select(args)
    except (ConfigError, UnsupportedSystem, ValueError) as exc:
        _error(str(exc))
        return 2
    if args.command == "setup":
        print("Saved profile.yaml. Preview with ./install.sh plan, apply with ./install.sh")
        return 0
    try:
        if args.command == "reinstall":
            return _reinstall(ctx, args.names)
        return Runner(ctx, args).run(tasks)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    except BrokenPipeError:  # output piped into `head` or a pager that quit
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 141
    finally:
        sudo.stop()


def _parse(argv: list[str] | None) -> argparse.Namespace:
    names = ", ".join(t.name for t in TASKS)
    p = argparse.ArgumentParser(
        prog="install.sh",
        description="Bring this machine in line with config.yaml. Safe to rerun at any time.",
        epilog=f"tasks, in run order: {names}",
    )
    p.add_argument(
        "command",
        nargs="?",
        default="apply",
        choices=("apply", "plan", "status", "upgrade", "reinstall", "setup", "cloud", "adopt", "catalog"),
        help="apply changes (default), show planned changes, summarise each task, "
        "apply and also upgrade everything installed (apt, mise tools, flatpaks, .debs), "
        "reinstall the named apps, tools or packages, "
        "answer the machine profile questions again, set up a Claude Code cloud environment "
        "(applies cloud.yaml), adopt existing config files into the repo, "
        "or print the web configurator's choices as JSON",
    )
    p.add_argument(
        "names",
        nargs="*",
        help="adopt: files or directories under $HOME; reinstall: apps, tools or packages",
    )
    p.add_argument("--module", help="adopt: module name under home/ (default: guessed from the path)")
    p.add_argument("--config", type=Path, help="config file (default: config.yaml)")
    p.add_argument("--only", type=_csv, default=[], metavar="TASK,..", help="run only these tasks")
    p.add_argument("--skip", type=_csv, default=[], metavar="TASK,..", help="skip these tasks")
    once = p.add_mutually_exclusive_group()
    once.add_argument("--no-once", action="store_true", help="skip one-time tasks")
    once.add_argument("--once-only", action="store_true", help="run only one-time tasks")
    p.add_argument("--rerun", type=_csv, default=[], metavar="TASK,..", help="run one-time tasks again")
    p.add_argument("-v", "--verbose", action="store_true", help="show every command and its output")
    prof = p.add_argument_group("machine profile (saved to profile.yaml; asked on the first run)")
    prof.add_argument("--role", choices=("desktop", "server"), help="server: CLI only, no GUI apps or fonts")
    prof.add_argument(
        "--persona",
        "--personas",
        dest="personas",
        type=_personas,
        metavar="NAME,..",
        help="toolsets from `personas` in config.yaml, e.g. node,k8s (`none` for the base only)",
    )
    for name, what in (("gpu", "NVIDIA driver + CUDA"), ("docker", "Docker Engine"), ("heavy", "heavy apps")):
        prof.add_argument(f"--{name}", action=argparse.BooleanOptionalAction, help=what)
    prof.add_argument(
        "--skip-apps",
        dest="skip_apps",
        type=_personas,
        metavar="NAME,..",
        help="apps from `apps` in config.yaml to leave out of this machine (`none` to skip nothing)",
    )
    prof.add_argument(
        "--harden",
        choices=("none", "standard", "aggressive"),
        help="Linux Mint: debloat and harden with scripts/mint/harden.sh",
    )
    prof.add_argument(
        "--cinnamon",
        action=argparse.BooleanOptionalAction,
        help="Linux Mint Cinnamon: apply the saved desktop look (desktop/cinnamon/)",
    )
    prof.add_argument("-y", "--yes", action="store_true", help="don't ask: use detected defaults")
    return p.parse_args(argv)


def _adopt(args: argparse.Namespace) -> int:
    if not args.names:
        _error("adopt needs at least one path, e.g. ./install.sh adopt ~/.config/htop")
        return 2
    config = _config_path(args)
    try:
        paths = [Path(name) for name in args.names]
        messages = adopt(paths, repo=REPO, home=Path.home(), config=config, module=args.module)
    except AdoptError as exc:
        _error(str(exc))
        return 2
    print("\n".join(messages))
    return 0


def _reinstall(ctx: Context, names: list[str]) -> int:
    if not names:
        _error("reinstall needs at least one name, e.g. ./install.sh reinstall ghostty node")
        return 2
    try:
        changes = reinstall.plan(ctx, names)
        for change in changes:
            print(f"  {change.summary}", flush=True)
            change.apply()
    except ConfigError as exc:
        _error(str(exc))
        return 2
    except (CommandError, OSError) as exc:
        _error(f"{exc}\n{getattr(exc, 'output', '').strip()}".strip())
        return 1
    print(f"Done: {len(changes)} reinstalled.")
    return 0


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _personas(value: str) -> list[str]:
    return [] if value.strip() in ("none", "") else _csv(value)


def _config_path(args: argparse.Namespace) -> Path:
    return (args.config or REPO / "config.yaml").resolve()


def _overlay_path(config_path: Path) -> Path:
    return config_path.with_name(f"{config_path.stem}.local.yaml")


def _use_cloud_overlay(config_path: Path) -> None:
    """Link the local overlay to the committed cloud.yaml, so later runs keep using it."""
    overlay = _overlay_path(config_path)
    cloud = REPO / "cloud.yaml"
    if overlay.is_symlink() and overlay.resolve() == cloud.resolve():
        return
    if overlay.exists() or overlay.is_symlink():
        raise ConfigError(f"{overlay} already exists; move its settings into cloud.yaml or delete it")
    overlay.symlink_to(os.path.relpath(cloud, overlay.parent))


def _context(args: argparse.Namespace) -> Context:
    config_path = _config_path(args)
    overlay = _overlay_path(config_path)
    profile_path = config_path.with_name("profile.yaml")
    config = load(config_path, overlay, home_dir=REPO / "home", profile=profile_path)
    facts = detect()
    config = _profile(args, config, facts, profile_path)
    home = Path.home()
    return Context(
        config=resolve(config, nvidia_gpu=facts.nvidia_gpu),
        facts=facts,
        repo=REPO,
        home=home,
        state=State(home / ".local" / "state" / "dotfiles" / "state.json"),
        run_id=datetime.now().strftime("%Y%m%d-%H%M%S"),
        apt=Apt(facts),
    )


def _profile(args: argparse.Namespace, config: Config, facts: Facts, path: Path) -> Config:
    """Make sure the config has a machine profile, asking for one on the first run."""
    keys = _profile_keys()
    given = {k: getattr(args, k) for k in (*keys, "skip_apps") if getattr(args, k) is not None}
    fresh = config.profile is None
    missing = frozenset() if fresh else _unanswered(path, keys)
    if missing and args.command in _ONBOARDING and not given:
        # profile.yaml predates a question: ask just that one, keep the other answers.
        tty = onboard.terminal() if not args.yes else None
        profile = onboard.onboard(config, facts, given={}, tty=tty, only=missing)
        if tty is None:
            # Nobody to ask (CI, no terminal, -y): use the defaults for this run only, so
            # the question is still asked the next time a terminal is attached.
            answers = ", ".join(f"{k}: {getattr(profile, k)}" for k in sorted(missing))
            print(f"note: {path.name} has no answer for {answers} (default, not saved); ./install.sh setup")
        else:
            onboard.save(path, profile, config.user)
        return replace(config, profile=profile)
    if not (fresh or given or args.command == "setup"):
        return config
    if fresh and args.command == "status":
        print(f"note: no {path.name} yet; showing detected defaults (./install.sh setup to choose)")
        return replace(config, profile=onboard.onboard(config, facts, given=given, tty=None))
    asking = args.command == "setup" or (fresh and args.command in _ONBOARDING)
    tty = onboard.terminal() if asking and not args.yes else None
    profile = onboard.onboard(config, facts, given=given, tty=tty)
    # Identity is asked with the other questions; a flags-only change keeps what is saved.
    user = onboard.identity(config, tty, onboard.git_identity()) if asking else config.user
    onboard.save(path, profile, user)
    if tty is None and fresh:
        print(f"note: wrote {path.name} from detected defaults; edit it or run ./install.sh setup")
    return replace(config, profile=profile, user=user)


def _profile_keys() -> list[str]:
    """The profile answers that are questions (skip_apps is only ever set by a flag)."""
    return [f.name for f in fields(Profile) if f.name != "skip_apps"]


def _unanswered(path: Path, keys: list[str]) -> frozenset[str]:
    """Profile answers that ``path`` doesn't contain yet."""
    try:
        saved = (yaml.safe_load(path.read_text()) or {}).get("profile") or {}
    except (OSError, yaml.YAMLError, AttributeError):
        return frozenset()
    return frozenset(k for k in keys if k not in saved)


def _select(args: argparse.Namespace) -> list[Task]:
    known = [t.name for t in TASKS]
    for name in (*args.only, *args.skip, *args.rerun):
        if name not in known:
            raise ConfigError(f"unknown task {name!r} (tasks: {', '.join(known)})")
    tasks = [t for t in TASKS if (not args.only or t.name in args.only) and t.name not in args.skip]
    if args.no_once:
        tasks = [t for t in tasks if not t.once or t.name in args.rerun]
    if args.once_only:
        tasks = [t for t in tasks if t.once]
    return tasks


class Runner:
    def __init__(self, ctx: Context, args: argparse.Namespace) -> None:
        self.ctx = ctx
        self.command = args.command
        self.rerun = set(args.rerun)
        self.applying = self.command in ("apply", "upgrade")
        if self.command == "upgrade":
            self.rerun.add("upgrade")  # the one-time apt full-upgrade task
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def run(self, tasks: list[Task]) -> int:
        ctx = self.ctx
        shells = ", ".join(
            f"{s} (default)" if s == ctx.config.shells.default else s for s in ctx.config.shells.install
        )
        print(self._paint("1", f"dotfiles {self.command}") + f"  {ctx.facts.pretty} · {shells}")
        if ctx.config.profile:
            p = ctx.config.profile
            extras = [*p.personas, *(name for name in ("gpu", "docker", "heavy") if getattr(p, name))]
            if p.harden != "none":
                extras.append("harden" if p.harden == "standard" else "harden:aggressive")
            if p.cinnamon and ctx.facts.distro_id == "linuxmint":
                extras.append("cinnamon")
            print(self._paint("2", f"  profile: {p.role}{''.join(f' +{e}' for e in extras)} (profile.yaml)"))

        changed = unchanged = 0
        for task in tasks:
            if not task.enabled(ctx):
                if self.command == "status":
                    self._line("-", task.name, "disabled")
                continue
            try:
                did_change = self._run_task(task)
            except BrokenPipeError:
                raise  # nobody is reading the output: not a task failure
            except (CommandError, OSError) as exc:  # OSError covers network failures too
                self._line("!", task.name, str(exc))
                tail = getattr(exc, "output", "").strip().splitlines()[-25:]
                print("\n".join(f"      {line}" for line in tail))
                ctx.state.save()
                print(self._paint("31", "Failed.") + " Fix the error above and rerun; finished work is kept.")
                return 1
            changed += did_change
            unchanged += not did_change

        if self.applying:
            ctx.state.save()
            print(f"Done: {changed} changed, {unchanged} unchanged.")
        else:
            print(f"Plan: {changed} to change, {unchanged} unchanged.")
        for note in ctx.notes:
            print(self._paint("33", "note: ") + note)
        return 0

    def _run_task(self, task: Task) -> bool:
        """Plan (and when applying, execute) one task. Returns True if it had changes."""
        ctx = self.ctx
        print_id = fingerprint(task.fingerprint(ctx))
        record = ctx.state.once_record(task.name) if task.once else None
        if record and record["fingerprint"] == print_id and task.name not in self.rerun:
            self._line("=", task.name, f"done {record['at'][:10]} (one-time; --rerun {task.name})")
            return False

        changes = task.plan(ctx)
        if self.command == "upgrade":
            changes = [*changes, *task.upgrade(ctx)]
        if not changes:
            self._line("=", task.name, "ok")
        elif self.command == "status":
            self._line("+", task.name, f"{len(changes)} pending")
        else:
            self._line("+", task.name, task.summary if self.command == "plan" else "")
            for change in changes:
                print(f"      {change.summary}", flush=True)
                if self.applying:
                    change.apply()

        if self.applying:
            task.commit(ctx)
            if task.once:
                ctx.state.mark_once(task.name, print_id)
            ctx.state.save()
        return bool(changes)

    def _line(self, mark: str, name: str, detail: str) -> None:
        color = {"=": "2", "+": "32", "!": "31", "-": "2"}[mark]
        print(f"  {self._paint(color, mark)} {name:<9} {self._paint('2', detail)}".rstrip(), flush=True)

    def _paint(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color and text else text


def _error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
