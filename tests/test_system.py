"""Distro detection: every Debian or Ubuntu derivative maps to an upstream release."""

from __future__ import annotations

import pytest

from dotkit import system
from dotkit.system import UnsupportedSystem, detect


def _detect(tmp_path, text: str):
    path = tmp_path / "os-release"
    path.write_text(text)
    return detect(path)


@pytest.mark.parametrize(
    ("os_release", "distro", "distro_id", "codename", "version"),
    [
        ("ID=ubuntu\nVERSION_CODENAME=noble\n", "ubuntu", "ubuntu", "noble", ""),
        ("ID=debian\nVERSION_ID=12\nVERSION_CODENAME=bookworm\n", "debian", "debian", "bookworm", "12"),
        ("ID=debian\nVERSION_ID=13\nVERSION_CODENAME=trixie\n", "debian", "debian", "trixie", "13"),
        # Derivatives name their upstream release.
        (
            'ID=linuxmint\nID_LIKE="ubuntu debian"\nVERSION_CODENAME=zara\nUBUNTU_CODENAME=noble\n',
            "ubuntu",
            "linuxmint",
            "noble",
            "",
        ),
        ('ID=pop\nID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble\n', "ubuntu", "pop", "noble", ""),
        (
            "ID=linuxmint\nID_LIKE=debian\nVERSION_CODENAME=gigi\nDEBIAN_CODENAME=trixie\n",
            "debian",
            "linuxmint",
            "trixie",
            "13",
        ),
        ("ID=raspbian\nID_LIKE=debian\nVERSION_CODENAME=bookworm\n", "debian", "raspbian", "bookworm", "12"),
        # A release newer than this table still reports its own version.
        ("ID=debian\nVERSION_ID=15\nVERSION_CODENAME=duke\n", "debian", "debian", "duke", "15"),
        # Rolling derivatives have no upstream codename: vendor repos get the newest stable.
        (
            "ID=kali\nID_LIKE=debian\nVERSION_ID=2026.3\nVERSION_CODENAME=kali-rolling\n",
            "debian",
            "kali",
            system.DEBIAN_STABLE,
            system.DEBIAN_RELEASES[system.DEBIAN_STABLE],
        ),
        (
            "ID=debian\nPRETTY_NAME=x\n",  # no codename at all (some minimal images)
            "debian",
            "debian",
            system.DEBIAN_STABLE,
            system.DEBIAN_RELEASES[system.DEBIAN_STABLE],
        ),
    ],
)
def test_derivatives_map_to_their_upstream_release(
    tmp_path, os_release, distro, distro_id, codename, version
):
    facts = _detect(tmp_path, os_release)
    assert (facts.distro, facts.distro_id, facts.codename, facts.version) == (
        distro,
        distro_id,
        codename,
        version,
    )


def test_other_distro_families_are_refused_with_a_clear_message(tmp_path):
    with pytest.raises(UnsupportedSystem, match="unsupported distro 'fedora'"):
        _detect(tmp_path, "ID=fedora\nID_LIKE=rhel\n")
