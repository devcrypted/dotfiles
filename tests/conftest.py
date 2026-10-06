from __future__ import annotations

from pathlib import Path

import pytest

from dotkit.apt import Apt
from dotkit.config import Config, Shells
from dotkit.state import State
from dotkit.system import Facts
from dotkit.tasks import Context

FACTS = Facts(
    distro="ubuntu",
    distro_id="ubuntu",
    codename="noble",
    version="",
    arch="amd64",
    user="tester",
    wsl=False,
    nvidia_gpu=False,
)


@pytest.fixture
def make_ctx(tmp_path: Path):
    """Build a Context with a throwaway HOME and repo under tmp_path."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    home.mkdir()
    (repo / "home").mkdir(parents=True)

    def _make(config: Config | None = None) -> Context:
        config = config or Config(shells=Shells(default="bash", install=("bash",)))
        return Context(
            config=config,
            facts=FACTS,
            repo=repo,
            home=home,
            state=State(home / ".local/state/dotfiles/state.json"),
            run_id="run1",
            apt=Apt(FACTS),
        )

    return _make


def write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def apply(changes) -> None:
    for change in changes:
        change.apply()
