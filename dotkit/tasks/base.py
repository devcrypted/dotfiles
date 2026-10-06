"""The task protocol every installer step implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ..apt import Apt
from ..config import Config
from ..fsops import display
from ..state import State
from ..system import Facts


@dataclass
class Context:
    """Everything a task may look at or touch during one run."""

    config: Config
    facts: Facts
    repo: Path
    home: Path
    state: State
    run_id: str
    apt: Apt
    notes: list[str] = field(default_factory=list)

    @property
    def backup_dir(self) -> Path:
        return self.state.path.parent / "backups" / self.run_id

    def show(self, path: Path) -> str:
        return display(path, self.home)

    def note(self, message: str) -> None:
        """Queue a message for the end-of-run summary (deduplicated)."""
        if message not in self.notes:
            self.notes.append(message)


@dataclass(frozen=True)
class Change:
    """One pending change: a human summary plus the callable that performs it."""

    summary: str
    apply: Callable[[], object]


class Task(ABC):
    """A unit of desired state.

    ``plan`` inspects the system and returns the changes still needed; an empty list
    means the task is already satisfied. ``plan`` must never modify anything, so
    ``./install.sh plan`` is always safe.
    """

    name: ClassVar[str]
    summary: ClassVar[str]
    #: One-time tasks are skipped after a successful run until their fingerprint changes.
    once: ClassVar[bool] = False

    def enabled(self, ctx: Context) -> bool:
        return True

    def packages(self, ctx: Context) -> Iterable[str]:
        """apt packages from the distro archive this task needs; installed by `packages`."""
        return ()

    def fingerprint(self, ctx: Context) -> object:
        """Config that, when changed, makes a completed one-time task pending again."""
        return None

    @abstractmethod
    def plan(self, ctx: Context) -> list[Change]: ...

    def commit(self, ctx: Context) -> None:
        """Record bookkeeping after a successful apply (runs even with no changes)."""
