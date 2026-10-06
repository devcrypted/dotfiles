"""Task registry. Order matters: tasks run top to bottom."""

from __future__ import annotations

from .base import Change, Context, Task
from .docker import Docker
from .fonts import Fonts
from .git import Git
from .hooks import Hooks
from .links import Links
from .mise import Mise
from .nvidia import Nvidia
from .packages import Packages
from .repos import Repos
from .shellenv import ShellEnv
from .shells import Shells
from .ssh import Ssh
from .sudo import Sudo
from .upgrade import Upgrade

TASKS: tuple[Task, ...] = (
    Upgrade(),
    Packages(),
    Repos(),
    Links(),  # before shells: prunes stale rc symlinks so shells can write real files
    ShellEnv(),
    Shells(),
    Git(),
    Hooks(),  # after git: commits need an identity
    Mise(),
    Fonts(),
    Docker(),
    Nvidia(),  # after docker: the container toolkit registers itself with Docker
    Ssh(),
    Sudo(),
)

__all__ = ["TASKS", "Change", "Context", "Task"]
