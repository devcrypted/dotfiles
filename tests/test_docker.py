from __future__ import annotations

import pytest

from dotkit.apt import Apt
from dotkit.config import Config, Docker
from dotkit.tasks import docker
from dotkit.tasks.docker import Docker as DockerTask


@pytest.fixture
def ctx(make_ctx, monkeypatch):
    monkeypatch.setattr(docker, "_in_docker_group", lambda user: True)
    return make_ctx(Config(docker=Docker(enabled=True)))


def _setup(monkeypatch, *, cli=True, buildx=True, ce=False, distro_buildx=True):
    monkeypatch.setattr(docker.shutil, "which", lambda name: "/usr/bin/docker" if cli else None)
    monkeypatch.setattr(docker, "_has_buildx", lambda: buildx)
    monkeypatch.setattr(Apt, "installed", staticmethod(lambda names: {"docker-ce-cli"} if ce else set()))
    monkeypatch.setattr(Apt, "available", staticmethod(lambda name: distro_buildx))


def test_nothing_to_do_when_buildx_present(ctx, monkeypatch):
    _setup(monkeypatch)
    assert DockerTask().plan(ctx) == []


def test_distro_docker_without_buildx_gets_distro_package(ctx, monkeypatch):
    _setup(monkeypatch, buildx=False)
    assert [c.summary for c in DockerTask().plan(ctx)] == ["install docker-buildx (docker buildx)"]


def test_docker_com_engine_gets_plugin_package(ctx, monkeypatch):
    _setup(monkeypatch, buildx=False, ce=True)
    assert "docker-buildx-plugin" in DockerTask().plan(ctx)[0].summary


def test_no_package_available_notes_instead_of_failing(ctx, monkeypatch):
    _setup(monkeypatch, buildx=False, distro_buildx=False)
    assert DockerTask().plan(ctx) == []
    assert any("buildx is missing" in n for n in ctx.notes)


def test_fresh_machine_installs_engine_only(ctx, monkeypatch):
    _setup(monkeypatch, cli=False, buildx=False)
    assert [c.summary for c in DockerTask().plan(ctx)] == ["install Docker Engine (includes buildx)"]
