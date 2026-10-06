from __future__ import annotations

from conftest import FACTS

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
