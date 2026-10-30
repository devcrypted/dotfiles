from __future__ import annotations

from dataclasses import replace

import pytest
from conftest import FACTS

from dotkit.config import Config, Harden, Profile
from dotkit.tasks import harden
from dotkit.tasks.harden import Harden as HardenTask

MINT = replace(FACTS, distro_id="linuxmint")
PREVIEW = """Linux Mint hardening  Linux Mint 22.3 · preview

== debloat ==
  ! keeping mintwelcome: removing it would also remove mint-meta-cinnamon
  ~ purge hexchat thunderbird (preview)

== firewall ==
  ufw is on and denies incoming

== kernel ==
  ~ write /etc/sysctl.d/60-dotfiles-hardening.conf (preview)

Preview only: 2 change(s) listed. Run again with --apply to make them.
"""


@pytest.fixture
def ctx(make_ctx):
    ctx = make_ctx(Config(profile=Profile(harden="aggressive"), harden=Harden(skip=("firewall",))))
    ctx.facts = MINT
    script = ctx.repo / "scripts/mint/harden.sh"
    script.parent.mkdir(parents=True)
    script.write_text("#!/bin/sh\n")
    return ctx


def test_runs_only_on_mint_when_the_profile_asks(ctx):
    assert HardenTask().enabled(ctx)
    ctx.facts = FACTS
    assert not HardenTask().enabled(ctx)
    ctx.facts = MINT
    ctx.config = replace(ctx.config, profile=Profile(harden="none"))
    assert not HardenTask().enabled(ctx)


def test_plan_is_the_scripts_preview(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(harden, "output", lambda argv, any_exit: calls.append(argv) or PREVIEW)
    applied = []
    monkeypatch.setattr(harden, "run", lambda argv, **kw: applied.append((argv, kw)))
    [change] = HardenTask().plan(ctx)
    assert change.summary == (
        "debloat and harden (2 changes: purge hexchat thunderbird; "
        "write /etc/sysctl.d/60-dotfiles-hardening.conf)"
    )
    script = str(ctx.repo / "scripts/mint/harden.sh")
    assert calls == [[script, "--aggressive", "--skip", "firewall"]]
    change.apply()
    # calls_sudo: the password is asked before the status line can draw over the prompt.
    assert applied == [
        ([script, "--aggressive", "--skip", "firewall", "--apply", "--yes"], {"calls_sudo": True})
    ]


def test_nothing_listed_means_nothing_to_do(ctx, monkeypatch):
    monkeypatch.setattr(harden, "output", lambda argv, any_exit: "Preview only: 0 change(s) listed.\n")
    assert HardenTask().plan(ctx) == []


def test_editing_the_script_makes_it_run_again(ctx):
    before = HardenTask().fingerprint(ctx)
    (ctx.repo / "scripts/mint/harden.sh").write_text("#!/bin/sh\necho changed\n")
    assert HardenTask().fingerprint(ctx) != before
