"""apt/dpkg helpers: query installed packages, install, and manage third-party repos."""

from __future__ import annotations

import base64
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .system import Facts, fetch, output, run

KEYRINGS = Path("/etc/apt/keyrings")
SOURCES = Path("/etc/apt/sources.list.d")
SOURCES_LIST = Path("/etc/apt/sources.list")
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
        self.drop_duplicates()
        run(["apt-get", "update"], root=True)
        self._fresh = True

    def install(self, packages: Iterable[str]) -> None:
        if not self._fresh:
            self.update()
        run(["apt-get", "install", "-y", *packages], root=True, env=_NONINTERACTIVE)
        # Some vendor packages (Brave, VS Code, Chrome) add their own source on install.
        self.drop_duplicates()

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
        """True when our source is in place, or another one already serves the same URL."""
        if self.other_source(name, line):
            return True
        source = SOURCES / f"{name}.list"
        return (KEYRINGS / f"{name}.gpg").exists() and source.exists() and source.read_text() == line

    def ensure_repo(self, name: str, key_url: str, line: str) -> None:
        if not self.repo_current(name, line):
            self.add_repo(name, key_url, line)

    @staticmethod
    def other_source(name: str, line: str) -> Path | None:
        """A source file we didn't write that points at the same repo URL as ``line``.

        apt refuses to run when two entries for one URL name different keyrings
        ("Conflicting values set for option Signed-By"), so ours must give way.
        """
        url = _repo_url(line)
        ours = SOURCES / f"{name}.list"
        files = [SOURCES_LIST, *sorted(SOURCES.glob("*.list")), *sorted(SOURCES.glob("*.sources"))]
        for path in files:
            if path == ours:
                continue
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            for entry in text.splitlines():
                if entry.lstrip().startswith("#"):
                    continue
                if any(token.rstrip("/") == url for token in entry.replace("]", " ").split()):
                    return path
        return None

    def duplicates(self) -> dict[str, Path]:
        """Our sources that another source file now also provides: name -> that file."""
        found = {}
        for path in sorted(SOURCES.glob("*.list")):
            try:
                line = path.read_text()
            except OSError:
                continue
            if f"signed-by={KEYRINGS / path.stem}.gpg" in line:  # written by add_repo
                other = self.other_source(path.stem, line)
                if other:
                    found[path.stem] = other
        return found

    def drop_duplicates(self) -> None:
        for name in self.duplicates():
            self.remove_repo(name)

    def add_repo(self, name: str, key_url: str, line: str) -> None:
        key = dearmor(fetch(self.facts.template(key_url)))
        _install_file(KEYRINGS / f"{name}.gpg", key)
        _install_file(SOURCES / f"{name}.list", line.encode())
        self._fresh = False

    def remove_repo(self, name: str) -> None:
        run(["rm", "-f", str(SOURCES / f"{name}.list"), str(KEYRINGS / f"{name}.gpg")], root=True)
        self._fresh = False


def _repo_url(line: str) -> str:
    """The URL in a one-line ``deb [options] URL suite components`` entry."""
    rest = line.split("]", 1)[-1].split()
    return rest[0].rstrip("/") if rest else ""


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
