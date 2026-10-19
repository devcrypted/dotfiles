from __future__ import annotations

import pytest
from conftest import FACTS

from dotkit import apt
from dotkit.apt import Apt, dearmor

ARMORED = b"""-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: test

aGVsbG8g
d29ybGQ=
=abcd
-----END PGP PUBLIC KEY BLOCK-----
"""


def test_dearmor_decodes_body_and_ignores_headers_and_checksum():
    assert dearmor(ARMORED) == b"hello world"


def test_dearmor_passes_binary_through():
    raw = b"\x99\x02\x0d\x04"
    assert dearmor(raw) == raw


def test_source_line_templates():
    line = Apt(FACTS).source_line("docker", "https://x/linux/{distro}", "{codename}", "stable")
    assert line == (
        "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://x/linux/ubuntu noble stable\n"
    )


def test_source_line_flat_repo_without_components():
    line = Apt(FACTS).source_line("nv", "https://n/deb/{arch}", "/")
    assert line.endswith("https://n/deb/amd64 /\n")


BRAVE = "https://brave-browser-apt-release.s3.brave.com/"
VENDOR_SOURCES = f"""Types: deb
URIs: {BRAVE}
Suites: stable
Components: main
Signed-By: /usr/share/keyrings/brave-browser-archive-keyring.gpg
"""


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(apt, "SOURCES", tmp_path / "sources.list.d")
    monkeypatch.setattr(apt, "KEYRINGS", tmp_path / "keyrings")
    monkeypatch.setattr(apt, "SOURCES_LIST", tmp_path / "sources.list")
    (tmp_path / "sources.list.d").mkdir()
    (tmp_path / "keyrings").mkdir()
    return tmp_path / "sources.list.d"


def _ours(sources):
    a = Apt(FACTS)
    line = a.source_line("brave", BRAVE, "stable", "main")
    (sources / "brave.list").write_text(line)
    (apt.KEYRINGS / "brave.gpg").write_bytes(b"k")
    return a, line


def test_vendor_source_for_same_url_counts_as_current(sources):
    a, line = _ours(sources)
    assert a.other_source("brave", line) is None and a.duplicates() == {}
    (sources / "brave-browser-release.sources").write_text(VENDOR_SOURCES)
    assert a.other_source("brave", line) == sources / "brave-browser-release.sources"
    assert a.repo_current("brave", line)
    assert a.duplicates() == {"brave": sources / "brave-browser-release.sources"}


def test_commented_entries_and_other_urls_are_ignored(sources):
    a, _ = _ours(sources)
    (sources / "old.list").write_text(f"# deb {BRAVE} stable main\ndeb https://other.example/ stable main\n")
    assert a.duplicates() == {}


def test_drop_duplicates_removes_only_ours(sources, monkeypatch):
    a, _ = _ours(sources)
    (sources / "brave-browser-release.sources").write_text(VENDOR_SOURCES)
    removed = []
    monkeypatch.setattr(Apt, "remove_repo", lambda self, name: removed.append(name))
    a.drop_duplicates()
    assert removed == ["brave"]
