"""Command line entry point: ``apply`` (default), ``plan``, ``status``, ``setup``, ``cloud`` and ``adopt``."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import onboard, system
from .adopt import AdoptError, adopt
from .apt import Apt
from .config import Config, ConfigError, load, resolve
from .state import State, fingerprint
from .system import CommandError, Facts, UnsupportedSystem, detect, sudo
from .tasks import TASKS, Context, Task

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    system.verbose = args.verbose
    if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
        _error("run as your normal user, not with sudo; it asks for a password when needed")
        return 2
    if args.command == "adopt":
        return _adopt(args)
    if args.paths:
        _error(f"unexpected arguments: {' '.join(map(str, args.paths))} (only `adopt` takes paths)")
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
        return Runner(ctx, args).run(tasks)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
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
        choices=("apply", "plan", "status", "setup", "cloud", "adopt"),
        help="apply changes (default), show planned changes, summarise each task, "
        "answer the machine profile questions again, set up a Claude Code cloud environment "
        "(applies cloud.yaml), or adopt existing config files into the repo",
    )
    p.add_argument("paths", nargs="*", type=Path, help="adopt: files or directories under $HOME")
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
    for name, what in (("gpu", "NVIDIA driver + CUDA"), ("docker", "Docker Engine"), ("heavy", "heavy apps")):
        prof.add_argument(f"--{name}", action=argparse.BooleanOptionalAction, help=what)
    prof.add_argument("-y", "--yes", action="store_true", help="don't ask: use detected defaults")
    return p.parse_args(argv)


def _adopt(args: argparse.Namespace) -> int:
    if not args.paths:
        _error("adopt needs at least one path, e.g. ./install.sh adopt ~/.config/htop")
        return 2
    config = _config_path(args)
    try:
        messages = adopt(args.paths, repo=REPO, home=Path.home(), config=config, module=args.module)
    except AdoptError as exc:
        _error(str(exc))
        return 2
    print("\n".join(messages))
    return 0


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


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
    given = {k: getattr(args, k) for k in ("role", "gpu", "docker", "heavy") if getattr(args, k) is not None}
    fresh = config.profile is None
    if not (fresh or given or args.command == "setup"):
        return config
    if fresh and args.command == "status":
        print(f"note: no {path.name} yet; showing detected defaults (./install.sh setup to choose)")
        return replace(config, profile=onboard.onboard(config, facts, given=given, tty=None))
    asking = args.command == "setup" or (fresh and args.command in ("apply", "plan"))
    tty = onboard.terminal() if asking and not args.yes else None
    profile = onboard.onboard(config, facts, given=given, tty=tty)
    onboard.save(path, profile)
    if tty is None and fresh:
        print(f"note: wrote {path.name} from detected defaults; edit it or run ./install.sh setup")
    return replace(config, profile=profile)


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
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def run(self, tasks: list[Task]) -> int:
        ctx = self.ctx
        shells = ", ".join(
            f"{s} (default)" if s == ctx.config.shells.default else s for s in ctx.config.shells.install
        )
        print(self._paint("1", f"dotfiles {self.command}") + f"  {ctx.facts.pretty} · {shells}")
        if ctx.config.profile:
            p = ctx.config.profile
            extras = [name for name in ("gpu", "docker", "heavy") if getattr(p, name)]
            print(self._paint("2", f"  profile: {p.role}{''.join(f' +{e}' for e in extras)} (profile.yaml)"))

        changed = unchanged = 0
        for task in tasks:
            if not task.enabled(ctx):
                if self.command == "status":
                    self._line("-", task.name, "disabled")
                continue
            try:
                did_change = self._run_task(task)
            except (CommandError, OSError) as exc:  # OSError covers network failures too
                self._line("!", task.name, str(exc))
                tail = getattr(exc, "output", "").strip().splitlines()[-25:]
                print("\n".join(f"      {line}" for line in tail))
                ctx.state.save()
                print(self._paint("31", "Failed.") + " Fix the error above and rerun; finished work is kept.")
                return 1
            changed += did_change
            unchanged += not did_change

        if self.command == "apply":
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
        if not changes:
            self._line("=", task.name, "ok")
        elif self.command == "status":
            self._line("+", task.name, f"{len(changes)} pending")
        else:
            self._line("+", task.name, task.summary if self.command == "plan" else "")
            for change in changes:
                print(f"      {change.summary}", flush=True)
                if self.command == "apply":
                    change.apply()

        if self.command == "apply":
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
