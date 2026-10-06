"""apt/dpkg helpers: query installed packages, install, and manage third-party repos."""

from __future__ import annotations

import base64
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .system import Facts, fetch, output, run

KEYRINGS = Path("/etc/apt/keyrings")
SOURCES = Path("/etc/apt/sources.list.d")
_NONINTERACTIVE = {"DEBIAN_FRONTEND": "noninteractive"}


class Apt:
    def __init__(self, facts: Facts) -> None:
        self.facts = facts
        self._fresh = False  # package index updated during this run?

    # -- packages ---------------------------------------------------------------------

    @staticmethod
    def installed(packages: Iterable[str]) -> set[str]:
        names = list(packages)
        if not names:
            return set()
        # dpkg-query exits 1 if any name is unknown but still reports the known ones.
        query = ["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\n", *names]
        lines = output(query, any_exit=True)
        return {
            name
            for name, _, status in (line.partition(" ") for line in lines.splitlines())
            if status.startswith("ii")
        }

    def missing(self, packages: Iterable[str]) -> list[str]:
        wanted = list(dict.fromkeys(packages))  # dedupe, keep order
        have = self.installed(wanted)
        return [p for p in wanted if p not in have]

    @staticmethod
    def available(package: str) -> bool:
        """True when some configured repo offers ``package``."""
        policy = output(["apt-cache", "policy", package])
        return "Candidate:" in policy and "Candidate: (none)" not in policy

    def update(self) -> None:
        run(["apt-get", "update"], root=True)
        self._fresh = True

    def install(self, packages: Iterable[str]) -> None:
        if not self._fresh:
            self.update()
        run(["apt-get", "install", "-y", *packages], root=True, env=_NONINTERACTIVE)

    def upgrade(self) -> None:
        self.update()
        run(["apt-get", "full-upgrade", "-y"], root=True, env=_NONINTERACTIVE)

    # -- third-party repositories -----------------------------------------------------

    def source_line(self, name: str, url: str, suite: str, components: str = "") -> str:
        f = self.facts
        parts = [
            f"deb [arch={f.arch} signed-by={KEYRINGS / name}.gpg]",
            f.template(url),
            f.template(suite),
            f.template(components),
        ]
        return " ".join(p for p in parts if p) + "\n"

    def repo_current(self, name: str, line: str) -> bool:
        source = SOURCES / f"{name}.list"
        return (KEYRINGS / f"{name}.gpg").exists() and source.exists() and source.read_text() == line

    def add_repo(self, name: str, key_url: str, line: str) -> None:
        key = dearmor(fetch(self.facts.template(key_url)))
        _install_file(KEYRINGS / f"{name}.gpg", key)
        _install_file(SOURCES / f"{name}.list", line.encode())
        self._fresh = False

    def remove_repo(self, name: str) -> None:
        run(["rm", "-f", str(SOURCES / f"{name}.list"), str(KEYRINGS / f"{name}.gpg")], root=True)
        self._fresh = False


def dearmor(data: bytes) -> bytes:
    """Convert an ASCII-armored OpenPGP key to binary (what ``gpg --dearmor`` does)."""
    if not data.lstrip().startswith(b"-----BEGIN PGP"):
        return data
    lines = data.decode("ascii").strip().splitlines()[1:]
    body, in_body = [], False
    for line in lines:
        if line.startswith("-----END"):
            break
        if not in_body:
            in_body = not line.strip()  # armor headers end at the first blank line
            continue
        if not line.startswith("="):  # "=XXXX" is the CRC24 checksum line
            body.append(line.strip())
    return base64.b64decode("".join(body))


def _install_file(dest: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(content)
        tmp.flush()
        run(["install", "-D", "-m", "0644", tmp.name, str(dest)], root=True)
