"""``install.sh adopt``: move existing config files into the repo and link them back.

This is how a new tool's config comes under management: the file moves to
home/<module>/<same path>, a symlink takes its place, and the module is enabled
in config.yaml so every future machine gets it too.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import SHELL_MODULES

# Content that suggests credentials. Matching files are adopted but flagged.
_SECRET_HINT = re.compile(rb"(?i)token|password|passwd|secret|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY")
_MODULE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MODULES_LINE = re.compile(r"^modules:[ \t]*\[(.*?)\]", re.M)


class AdoptError(Exception):
    """Nothing was moved: the request was invalid."""


def adopt(paths: list[Path], *, repo: Path, home: Path, config: Path, module: str | None) -> list[str]:
    """Adopt ``paths`` (files or directories) into ``module``. Returns messages for the user.

    Every path is validated before anything moves, so a bad argument changes nothing.
    """
    sources = [_check(Path(p).expanduser().absolute(), repo, home) for p in paths]
    name = module or _guess_module(sources, home)
    if not _MODULE_NAME.match(name):
        raise AdoptError(f"invalid module name {name!r} (use a-z, 0-9, ., _ and -)")

    files = sorted({f for s in sources for f in _files(s)})
    if not files:
        raise AdoptError("no regular files to adopt (symlinks are skipped)")
    moves = [(f, repo / "home" / name / f.relative_to(home)) for f in files]
    taken = [str(dest.relative_to(repo)) for _, dest in moves if dest.exists()]
    if taken:
        raise AdoptError(f"already in the repo: {', '.join(taken)}")

    for source, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, dest)
        source.symlink_to(dest)

    messages = [f"adopted ~/{s.relative_to(home)} -> home/{name}/" for s, _ in moves]
    if name not in SHELL_MODULES:
        if _enable_module(config, name):
            messages.append(f"enabled module {name!r} in {config.name}")
        else:
            messages.append(f"add {name!r} to `modules` in {config.name} so new machines get it")
    flagged = [f"home/{name}/{s.relative_to(home)}" for s, d in moves if _SECRET_HINT.search(d.read_bytes())]
    if flagged:
        messages.append(
            "WARNING: these may contain credentials; check before committing (or move secrets "
            f"to an untracked file): {', '.join(flagged)}"
        )
    messages.append(f"next: git add home/{name} {config.name} && git commit")
    return messages


def _check(path: Path, repo: Path, home: Path) -> Path:
    if not path.is_relative_to(home) or path == home:
        raise AdoptError(f"{path}: only files inside {home} can be adopted")
    if path.is_relative_to(repo):
        raise AdoptError(f"{path}: already inside the dotfiles repo")
    if path.is_symlink():
        raise AdoptError(f"{path}: is a symlink (already managed?); adopt the real file instead")
    if not path.exists():
        raise AdoptError(f"{path}: no such file or directory")
    return path


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [f for f in path.rglob("*") if f.is_file() and not f.is_symlink()]


def _guess_module(sources: list[Path], home: Path) -> str:
    """~/.config/<tool>/... -> <tool>; ~/.config/<tool>.toml -> <tool>. Otherwise ask."""
    names = set()
    for source in sources:
        parts = source.relative_to(home).parts
        if parts[0] != ".config" or len(parts) < 2:
            raise AdoptError(f"~/{'/'.join(parts)}: can't guess a module name; pass --module NAME")
        names.add(parts[1] if len(parts) > 2 or source.is_dir() else Path(parts[1]).stem)
    if len(names) > 1:
        raise AdoptError(f"paths belong to different tools ({', '.join(sorted(names))}); pass --module")
    return names.pop()


def _enable_module(config: Path, name: str) -> bool:
    """Append ``name`` to the `modules: [...]` line. False if that line isn't found."""
    text = config.read_text()
    match = _MODULES_LINE.search(text)
    if match is None:
        return False
    items = [i.strip() for i in match.group(1).split(",") if i.strip()]
    if name not in items:
        items.append(name)
        config.write_text(text[: match.start(1)] + ", ".join(items) + text[match.end(1) :])
    return True
